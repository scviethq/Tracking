# -*- encoding: utf-8 -*-

from odoo import api, fields, models, _
from shapely.geometry import Point
from datetime import timedelta, datetime

class FleetVehicleLogTracking(models.Model):
    _name = 'fleet.vehicle.tracking'
    _rec_name = 'serial'

    serial = fields.Char('Tracking Serial', required=True, default='/')
    provider = fields.Char('Tracking Provider', required=True)
    date_created = fields.Datetime(string="Created Date", default=fields.Datetime.now)
    gps_latitude = fields.Float('GPS Latitude',digits=(16, 5))
    gps_longitude = fields.Float('GPS Longitude',digits=(16, 5))
    gps_address = fields.Char(string='Address')
    geo_point = fields.GeoPoint('GeoPoint', srid=4326, copy=False, compute='_compute_geo_point',
                                inverse='_inverse_geo_point', compute_sudo=True)
    raw_data = fields.Text(string="GPS Raw Data")
    gps_speed = fields.Float('GPS Speed')
    km_date = fields.Float('KM in Date')
    gps_direction = fields.Float('GPS Direction')
    machine_power = fields.Selection([('on', 'On'),('off', 'Off')])
    humidity = fields.Float('Humidity')
    temperature = fields.Float('Temperature')

    @api.depends('gps_latitude','gps_longitude')
    def _compute_geo_point(self):
        for tracking in self:
            tracking.geo_point = Point(tracking.gps_longitude, tracking.gps_latitude)

    @api.depends('geo_point')
    def _inverse_geo_point(self):
        for tracking in self:
            tracking.gps_latitude = tracking.geo_point.y
            tracking.gps_longitude = tracking.geo_point.x

    @api.model
    def autovacuum(self):
        deadline = datetime.now() - timedelta(days=int(1))
        recs = self.search([("create_date", "<=", deadline)])
        recs.unlink()

    @api.model
    def cron_update_data(self):
        # CALL GPS API Here to Collect Tracking Data
        self.env['tracking.provider'].update_tracking()
        # self.env['bus.bus'].sendone('map_monitoring', {
        #     'type': 'map_monitoring',
        #     'tracking_data': {}
        # })
