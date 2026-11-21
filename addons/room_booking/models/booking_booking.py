# Imports and constants: what this file needs, and the values the rules below share.
# ========================== Imports and Constants ===========================
import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

STATES_THAT_HOLD_THE_SLOT = ['requested', 'confirmed']
# R4: the status a booking may move to from each status. Completed and Cancelled are final.
ALLOWED_NEXT_STATES = {
    'requested': ['confirmed', 'cancelled'],
    'confirmed': ['completed', 'cancelled'],
}
BOOKING_MANAGER_GROUP = 'room_booking.group_booking_manager'
# Opening hours are office time (Bangkok). The database stores every Datetime in UTC.
OFFICE_TIMEZONE = pytz.timezone('Asia/Bangkok')
# ======================== End Imports and Constants =========================


# Time helpers: two small functions used by the opening-hours check (R3).
# =============================== Time Helpers ===============================

# Turn a Datetime from the database (UTC, no timezone attached) into office time.
# ------------------------------ to_office_time ------------------------------
def to_office_time(utc_datetime):
    return pytz.utc.localize(utc_datetime).astimezone(OFFICE_TIMEZONE)
# ---------------------------- End to_office_time ----------------------------

# Write an hour the way the form shows it: 8.5 -> '08:30'.
# ---------------------------- hour_to_clock_text ----------------------------
def hour_to_clock_text(float_hour):
    whole_hours, minutes = divmod(round(float_hour * 60), 60)
    return '%02d:%02d' % (whole_hours, minutes)
# -------------------------- End hour_to_clock_text --------------------------

# ============================= End Time Helpers =============================


# Data schema: the fields of a booking. Odoo builds the table booking_booking from it
# (one field = one column). Names with _ are model settings, the others are fields.
# =============================== Data Schema ================================
class BookingBooking(models.Model):
    """One booking of one resource for one time slot."""

    _name = 'booking.booking'
    _description = 'Booking'
    _order = 'start desc'

    name = fields.Char(string='Purpose', required=True)
    resource_id = fields.Many2one(
        'booking.resource',
        string='Resource',
        required=True,
        ondelete='restrict',
    )
    user_id = fields.Many2one(
        'res.users',
        string='Booked By',
        required=True,
        default=lambda self: self.env.user,
        copy=False,
    )
    start = fields.Datetime(required=True)
    stop = fields.Datetime(string='End', required=True)
    state = fields.Selection(
        [
            ('requested', 'Requested'),
            ('confirmed', 'Confirmed'),
            ('completed', 'Completed'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        required=True,
        default='requested',
        copy=False,
    )
# ============================= End Data Schema ==============================

    # Constraints: rules the data must follow, or Odoo cancels the save. A method named
    # _check_... validates data; the leading _ means Odoo calls it, not a user.
    # ============================= Constraints ==============================

    # End must come after Start. Odoo runs constraints in alphabetical order of their
    # names, so this one runs first, then _check_inside_opening_hours, then the R2 check.
    # ------------------------ _check_end_after_start ------------------------
    @api.constrains('start', 'stop')
    def _check_end_after_start(self):
        for booking in self:
            if booking.start and booking.stop and booking.stop <= booking.start:
                raise ValidationError(_('End must be after Start.'))
    # ---------------------- End _check_end_after_start ----------------------

    # R3: a booking must start and end inside its resource's opening hours (office time).
    # Minutes are counted from midnight of the start day, so ending after midnight is too late.
    # --------------------- _check_inside_opening_hours ----------------------
    @api.constrains('resource_id', 'start', 'stop')
    def _check_inside_opening_hours(self):
        for booking in self:
            if not booking.start or not booking.stop or not booking.resource_id:
                continue
            resource = booking.resource_id
            start_in_office = to_office_time(booking.start)
            end_in_office = to_office_time(booking.stop)
            start_day_midnight = start_in_office.replace(hour=0, minute=0, second=0, microsecond=0)
            start_minutes = (start_in_office - start_day_midnight).total_seconds() / 60
            end_minutes = (end_in_office - start_day_midnight).total_seconds() / 60
            opening_minutes = round(resource.open_from * 60)
            closing_minutes = round(resource.open_to * 60)
            if start_minutes < opening_minutes or end_minutes > closing_minutes:
                raise ValidationError(_(
                    '%(resource)s can be booked only from %(opens)s to %(closes)s '
                    'on the same day (Bangkok time). Choose a time inside these hours.',
                    resource=resource.name,
                    opens=hour_to_clock_text(resource.open_from),
                    closes=hour_to_clock_text(resource.open_to),
                ))
    # ------------------- End _check_inside_opening_hours --------------------

    # R2: one resource cannot have two active bookings at the same time.
    # Runs after every create and every write of these fields; an error rolls back the save.
    # ----------------------- _check_no_double_booking -----------------------
    @api.constrains('resource_id', 'start', 'stop', 'state')
    def _check_no_double_booking(self):
        for booking in self:
            if booking.state not in STATES_THAT_HOLD_THE_SLOT:
                continue
            conflicting_booking = self.search([
                ('id', '!=', booking.id),
                ('resource_id', '=', booking.resource_id.id),
                ('state', 'in', STATES_THAT_HOLD_THE_SLOT),
                ('start', '<', booking.stop),
                ('stop', '>', booking.start),
            ], limit=1)
            if conflicting_booking:
                raise ValidationError(_(
                    '%(resource)s is already booked at that time: "%(purpose)s" by %(user)s. '
                    'Choose another time or another resource.',
                    resource=booking.resource_id.name,
                    purpose=conflicting_booking.name,
                    user=conflicting_booking.user_id.name,
                ))
    # --------------------- End _check_no_double_booking ---------------------

    # =========================== End Constraints ============================

    # Lifecycle rules (R4): Odoo calls create() and write() on every save, from the form,
    # an import or the API, so the status rules live here and nobody can skip them.
    # =========================== Lifecycle Rules ============================

    # A new booking always starts as Requested, even if someone sends another status.
    # Odoo passes a list here: one dict of values per new booking.
    # -------------------------------- create --------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals['state'] = 'requested'
        return super().create(vals_list)
    # ------------------------------ End create ------------------------------

    # Check the change first, then let Odoo save it (super) as usual.
    # -------------------------------- write ---------------------------------
    def write(self, vals):
        if 'state' in vals:
            self._ensure_status_change_is_allowed(vals['state'])
        if not self._is_booking_manager():
            self._ensure_employee_may_edit(vals)
        return super().write(vals)
    # ------------------------------ End write -------------------------------

    # Manager, or Odoo itself running as superuser (code that uses sudo()).
    # ------------------------- _is_booking_manager --------------------------
    def _is_booking_manager(self):
        return self.env.su or self.env.user.has_group(BOOKING_MANAGER_GROUP)
    # ----------------------- End _is_booking_manager ------------------------

    # Only the moves in ALLOWED_NEXT_STATES, and only a manager may confirm or complete.
    # ------------------- _ensure_status_change_is_allowed -------------------
    def _ensure_status_change_is_allowed(self, new_state):
        # {'requested': 'Requested', ...}: the names shown in the error messages
        state_labels = dict(self._fields['state'].selection)
        for booking in self:
            if new_state == booking.state:
                continue  # sending the same status again is not a move
            if new_state not in ALLOWED_NEXT_STATES.get(booking.state, []):
                raise UserError(_(
                    'A booking cannot go from %(old)s to %(new)s.',
                    old=state_labels.get(booking.state, booking.state),
                    new=state_labels.get(new_state, new_state),
                ))
            if new_state in ('confirmed', 'completed') and not self._is_booking_manager():
                raise UserError(_(
                    'Only a Manager can mark a booking as %(new)s.',
                    new=state_labels.get(new_state, new_state),
                ))
    # ----------------- End _ensure_status_change_is_allowed -----------------

    # Employees keep their bookings in their own name, and change the resource or the
    # time only while the booking is still Requested.
    # ---------------------- _ensure_employee_may_edit -----------------------
    def _ensure_employee_may_edit(self, vals):
        if 'user_id' in vals and vals['user_id'] != self.env.user.id:
            raise UserError(_('You cannot give your booking to someone else.'))
        changes_slot = 'resource_id' in vals or 'start' in vals or 'stop' in vals
        if changes_slot and any(booking.state != 'requested' for booking in self):
            raise UserError(_(
                'You can change the resource or the time only while the booking is Requested. '
                'Cancel it and book again instead.'
            ))
    # -------------------- End _ensure_employee_may_edit ---------------------

    # ========================= End Lifecycle Rules ==========================

    # Buttons on the form. They only ask write() for the new status; write() checks it.
    # =============================== Buttons ================================

    # Confirm button, shown to Managers on a Requested booking.
    # ---------------------------- action_confirm ----------------------------
    def action_confirm(self):
        self.write({'state': 'confirmed'})
    # -------------------------- End action_confirm --------------------------

    # Cancel button. Employees can only write their own bookings (record rule),
    # so only the owner or a manager can cancel.
    # ---------------------------- action_cancel -----------------------------
    def action_cancel(self):
        self.write({'state': 'cancelled'})
    # -------------------------- End action_cancel ---------------------------

    # ============================= End Buttons ==============================
