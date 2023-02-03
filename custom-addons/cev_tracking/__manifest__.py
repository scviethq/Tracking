# -*- encoding: utf-8 -*-

{
    'name': 'CEV tracking',
    'version': '16.0.0',
    'author': 'Cloud Enterprise',
    'license': 'AGPL-3',
    'website': 'https://suitecloud.vn',
    'depends': [
    ],
    # "external_dependencies": {"python": ["openrouteservice"]},
    'data': [
        "views/tracking_provider.xml",
        "security/ir.model.access.csv",
        "data/data.xml",
    ],
    'qweb': [],
    'demo': [],
    'installable': True,
}
