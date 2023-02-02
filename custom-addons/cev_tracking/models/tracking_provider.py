# -*- encoding: utf-8 -*-
from datetime import datetime

import requests

from odoo import api, fields, models, _, tools
from odoo.exceptions import ValidationError
import json
DATE_TIME_FORMAT = tools.misc.DEFAULT_SERVER_DATETIME_FORMAT


class TrackingProvider(models.Model):
    _name = 'tracking.provider'

    name = fields.Char('Name', required=True, translate=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(help="Determine the display order", default=10)
    prod_environment = fields.Boolean("Environment", help="Set to True if your credentials are certified for production.")
    provider = fields.Selection(
        selection=[
            ('adsun', 'Adsun'),
            ('efento', 'Efento')
        ], string='Provider',
        default='adsun', required=True)
    state = fields.Selection([
        ('disabled', 'Disabled'),
        ('enabled', 'Enabled'),
        ('test', 'Test Mode')], required=True, default='disabled', copy=False,
        help="""In test mode, a fake provider API is processed through a test
                 payment interface. This mode is advised when setting up the
                 provider. Watch out, test and production modes require
                 different credentials.""")
    geo_info_template = fields.Char(string='Template Name')

    adsun_serv_page_code = fields.Char('Server Page Code', required_if_provider='adsun')
    adsun_serv_api_url = fields.Text('API URL', required_if_provider='adsun')
    adsun_serv_user_name = fields.Char('Username', required_if_provider='adsun')
    adsun_serv_password = fields.Char('Password', required_if_provider='adsun')

    efento_api_base_url = fields.Char(string="Api Base URL", required_if_provider='efento')
    efento_user_name = fields.Char(string='User name', required_if_provider='efento')
    efento_password = fields.Char(string='Password', required_if_provider='efento')

    @api.model
    def update_tracking(self):
        for gps in self.search([('state','!=','disabled')]):
            if hasattr(gps, '%s_update_tracking' % gps.provider):
                getattr(gps, '%s_update_tracking' % gps.provider)()

    @api.model
    def retrieve_alert(self, serial, from_date, to_date, vehicle_id):
        for gps in self.search([('state', '!=', 'disabled')]):
            if hasattr(gps, '%s_retrieve_alert' % gps.provider):
                getattr(gps, '%s_retrieve_alert' % gps.provider)(serial, from_date, to_date, vehicle_id)

    # ADSUN
    def adsun_update_tracking(self):
        self.ensure_one()
        gps_serv_api_url = self.adsun_serv_api_url
        if not gps_serv_api_url:
            return True

        params = {
            "pageIds": self.adsun_serv_page_code,
            "username": self.adsun_serv_user_name,
            "pwd": self.adsun_serv_password
        }
        res = requests.get(gps_serv_api_url, params=params)
        data = []
        if res.status_code == 200:
            data = json.loads(res.content).get('Data')
        for line in data:
            self.env['fleet.vehicle.tracking'].sudo().create({
                "serial": line.get('Id'),
                'gps_latitude': line.get('Lat', False),
                'gps_longitude': line.get('Lng', False),
                'gps_address': line.get('Address', False),
                'gps_speed': line.get('Speed', False),
                'gps_direction': line.get('Angle', False),
                'machine_power': 'on' if line.get('IsStop') else 'off',
                'raw_data': json.dumps(line),
                'provider': self.provider
            })

    # EFENTO
    def efento_get_access_tokens(self):
        headers = {
            "Content-type": "application/x-www-form-urlencoded",
            "X-USER-LOGIN": self.efento_user_name,
            "X-USER-PASSWORD": self.efento_password
        }

        response = requests.post("%s/%s" % (self.efento_api_base_url, 'login'), headers=headers)
        if response.status_code != 200:
            raise ValidationError(_(json.loads(response.content).get('message')))
        data = json.loads(response.content)
        return data.get('accessToken')

    def efento_update_tracking(self):
        def _get_messure_points(api_base_url, access_token):
            headers = {
                "Content-type": "application/x-www-form-urlencoded",
                "Authorization": "Bearer %s" % access_token
            }
            org_res = requests.get("%s/%s" % (api_base_url, 'organizations'), headers=headers)
            if org_res.status_code != 200:
                raise ValidationError(_(json.loads(org_res.content).get('message')))
            org_data = json.loads(org_res.content)
            organizations = [el.get('id') for el in org_data.get('organizations')]
            messure_points = []
            for organization_id in organizations:
                # Get locations
                loc_response = requests.get("%s/%s" % (api_base_url, 'locations'), headers=headers, params={"organization-id": organization_id})
                if loc_response.status_code != 200:
                    continue
                loc_data = json.loads(loc_response.content)
                locations = [el.get('id') for el in loc_data.get('locations')]
                for location_id in locations:
                    point_response = requests.get("%s/%s" % (api_base_url, 'measurement-points'), headers=headers,
                                            params={"location-ids": location_id})
                    if point_response.status_code != 200:
                        continue
                    point_data = json.loads(point_response.content)
                    messure_points += point_data.get("measurementPoints")

            return messure_points

        access_token = self.efento_get_access_tokens()
        messure_points = _get_messure_points(self.efento_api_base_url, access_token)

        for point in messure_points:
            temp_device = [device for device in point.get("measurements").get('channels') if
                           device.get("type") == 'TEMPERATURE']
            humi_device = [device for device in point.get("measurements").get('channels') if
                           device.get("type") == 'HUMIDITY']
            if not temp_device and not humi_device:
                continue
            created_time = point.get('createdAt')
            currentTime = fields.Datetime.now()
            # signal is off
            temp = temp_device and temp_device[0].get("value") or False
            humidity = humi_device and humi_device[0].get("value") or False
            if not created_time or ((datetime.strptime(created_time, DATE_TIME_FORMAT) - currentTime).seconds / 60) > 5:
                temp =  False
                humidity =  False
            vals = {
                "serial": "%s_%s" % (point.get('id'), point.get('name')),
                "temperature": temp,
                "humidity": humidity,
                'provider': self.provider,
                'raw_data' : json.dumps( {"serial":point.get('name'), "temperature":temp, "humidity": humidity})
            }

            self.env['fleet.vehicle.tracking'].sudo().create(vals)

    def efento_retrieve_alert(self, serial, from_date, to_date, vehicle_id):
        access_token = self.efento_get_access_tokens()
        headers = {
            "Content-type": "application/x-www-form-urlencoded",
            "Authorization": "Bearer %s" % access_token
        }
        measure_point_id = serial.split('_')[0]
        alert_response = requests.get("%s/%s" % (self.efento_api_base_url, 'alerts'), headers=headers,
                                      params={
                                          "select-by": "MEASUREMENT_POINTS",
                                          "select-by-ids": [measure_point_id],
                                          "from": from_date.strftime("%Y-%m-%d %H:%M:%I"),
                                          "to": to_date.strftime("%Y-%m-%d %H:%M:%I")
                                      })
        if alert_response.status_code != 200:
            return True
        alert_info = alert_response and json.loads(alert_response.content).get("alerts") or []
        for alert in alert_info:
            rule = alert.get("rule")
            rule_name = rule.get("name")
            rule_condition = rule.get("condition", False)
            alarm_time = datetime.strptime(alert.get("createdAt"), DATE_TIME_FORMAT)
            duration_time_delta = datetime.strptime(alert.get("neutralizedAt"), DATE_TIME_FORMAT) - alarm_time
            duration_time = round(duration_time_delta.seconds / 60)
            alert_id = alert.get('id')
            saved_alert_id = self.env['fleet.trip.alert'].search([('name', '=', alert_id)], limit=1)
            vals = {
                "criteria_type": rule.get("parameter", False),
                "device_serial": alert.get("serialNumber"),
                "level": "low" if rule_name == "Low Alarm" else "hight",
                "alarm_type": "more_than" if rule_condition == "MORE_THAN" else "less_than",
                "threshold": rule.get("threshold", 0),
                "value": alert.get("measurement"),
                "vehicle_id": vehicle_id,
                "alarm_time": alarm_time,
                "duration": duration_time,
                "is_confirmed": alert.get("confirmedAt") and True or False
            }
            if saved_alert_id:
                saved_alert_id.write(vals)
                continue
            vals.update({'name': alert_id})
            saved_alert = self.env['fleet.trip.alert'].create(vals)