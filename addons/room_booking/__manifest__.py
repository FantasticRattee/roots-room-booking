# Manifest: the ID card of the module. Odoo reads it first.
# ============================= Module Manifest ==============================
{
    # Name, version and category shown in the Apps list.
    # ----------------------------- Module Info ------------------------------
    'name': 'Room Booking',
    'version': '18.0.1.0.0',
    'summary': 'Book rooms and equipment for a time slot',
    'category': 'Productivity',
    'license': 'LGPL-3',
    # --------------------------- End Module Info ----------------------------
    # base: users and access rights.
    # ----------------------------- Dependencies -----------------------------
    'depends': ['base'],
    # --------------------------- End Dependencies ---------------------------
    # Files Odoo loads on install/upgrade, in this order
    # ------------------------------ Data Files ------------------------------
    'data': [
        'security/booking_security.xml',
        'security/ir.model.access.csv',
        'views/booking_resource_views.xml',
        'views/booking_booking_views.xml',
        'views/booking_menus.xml',
        'data/booking_resource_data.xml',
    ],
    # ---------------------------- End Data Files ----------------------------
    'application': True,
}
# =========================== End Module Manifest ============================
