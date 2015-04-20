# -*- coding: utf-8 -*-

{
    'name': 'Authorize.Net CIM Payment Acquirer',
    'category': 'Hidden',
    'summary': 'Payment Acquirer: Authorize.net CIM Implementation',
    'version': '1.0',
    'description': """Authorize.Net CIM Payment Acquirer""",
    'author': 'eNuke/CloudMy.IT LLC',
    'depends': ['payment'],
    'data': [
        'views/authorize_cim.xml',
        'views/payment_acquirer.xml',
        'data/authorize_cim.xml',
        'views/checkout_page_template.xml',
        'views/payment_page_override.xml',
        'security/ir.model.access.csv',
    ],
    'installable': True,
}
