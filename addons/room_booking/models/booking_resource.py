from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


# Data schema: the fields of a resource (a room or equipment). Odoo builds the table
# booking_resource from it. Names with _ are model settings, the others are fields.
# =============================== Data Schema ================================
class BookingResource(models.Model):
    """Something people can book: a room or a piece of equipment."""

    _name = 'booking.resource'
    _description = 'Bookable Resource'
    _order = 'name'

    name = fields.Char(required=True)
    resource_type = fields.Selection(
        [('room', 'Room'), ('equipment', 'Equipment')],
        string='Type',
        required=True,
        default='room',
    )
    open_from = fields.Float(string='Open From', default=8.0)
    open_to = fields.Float(string='Open To', default=18.0)
    active = fields.Boolean(default=True)
# ============================= End Data Schema ==============================

    # Constraints: rules the data must follow, or Odoo cancels the save.
    # R3: opening hours must be a time range inside one day, from 00:00 to 24:00.
    # ============================= Constraints ==============================
    @api.constrains('open_from', 'open_to')
    def _check_opening_hours_are_valid(self):
        for resource in self:
            if not (0 <= resource.open_from < resource.open_to <= 24):
                raise ValidationError(_(
                    'Opening hours must be between 00:00 and 24:00, '
                    'and Open From must be before Open To.'
                ))
    # =========================== End Constraints ============================
