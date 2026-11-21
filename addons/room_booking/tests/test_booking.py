# Imports and helpers. Each test runs in a transaction that Odoo rolls back at the end,
# so the tests never change the database. How to run them: see README.md.
# =========================== Imports and Helpers ============================
import datetime

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged

# The day every test booking uses (any day works: each test books its own new room).
FUTURE_DAY = datetime.date.today() + datetime.timedelta(days=30)


def bangkok_to_utc(day, hour):
    """The database stores UTC. Bangkok is UTC+7, so 09:00 Bangkok is 02:00 UTC."""
    return datetime.datetime.combine(day, datetime.time(0)) + datetime.timedelta(hours=hour - 7)
# ========================= End Imports and Helpers ==========================


# post_install: run after every module is installed, like a real database
@tagged('post_install', '-at_install')
class TestBooking(TransactionCase):

    # Test setup: three users and one room open 08:00-18:00, plus small helpers.
    # ============================== Test Setup ==============================

    # Runs once for the class. no_reset_password: do not send an invitation email.
    # ------------------------------ setUpClass ------------------------------
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        users = cls.env['res.users'].with_context(no_reset_password=True)
        employee_group = cls.env.ref('base.group_user')
        manager_group = cls.env.ref('room_booking.group_booking_manager')
        cls.employee = users.create({
            'name': 'Test Employee', 'login': 'test_employee',
            'groups_id': [(6, 0, [employee_group.id])],
        })
        cls.other_employee = users.create({
            'name': 'Other Employee', 'login': 'test_other_employee',
            'groups_id': [(6, 0, [employee_group.id])],
        })
        cls.manager = users.create({
            'name': 'Test Manager', 'login': 'test_manager',
            'groups_id': [(6, 0, [manager_group.id])],
        })
        cls.room = cls.env['booking.resource'].create({
            'name': 'Test Room', 'open_from': 8, 'open_to': 18,
        })
    # ---------------------------- End setUpClass ----------------------------

    # Create a booking as `user`, with times given in Bangkok hours (9.5 = 09:30).
    # --------------------------------- book ---------------------------------
    def book(self, user, start_hour, end_hour, day=FUTURE_DAY, end_day=None, resource=None):
        return self.env['booking.booking'].with_user(user).create({
            'name': 'Test booking',
            'resource_id': (resource or self.room).id,
            'start': bangkok_to_utc(day, start_hour),
            'stop': bangkok_to_utc(end_day or day, end_hour),
        })
    # ------------------------------- End book -------------------------------

    # Move a booking to new Bangkok hours on FUTURE_DAY, as `user`.
    # --------------------------------- move ---------------------------------
    def move(self, booking, user, start_hour, end_hour):
        booking.with_user(user).write({
            'start': bangkok_to_utc(FUTURE_DAY, start_hour),
            'stop': bangkok_to_utc(FUTURE_DAY, end_hour),
        })
    # ------------------------------- End move -------------------------------

    # ============================ End Test Setup ============================

    # R1: employees create and edit only their own bookings; only managers delete
    # bookings or change resources.
    # ========================== R1 Access Control ===========================

    # The record rule lets an employee change their own booking.
    # ------------------- test_employee_edits_own_booking --------------------
    def test_employee_edits_own_booking(self):
        booking = self.book(self.employee, 9, 10)
        booking.with_user(self.employee).write({'name': 'Renamed'})
        self.assertEqual(booking.name, 'Renamed')
    # ----------------- End test_employee_edits_own_booking ------------------

    # The record rule blocks changes to another person's booking.
    # ----------- test_employee_cannot_edit_someone_elses_booking ------------
    def test_employee_cannot_edit_someone_elses_booking(self):
        booking = self.book(self.other_employee, 9, 10)
        with self.assertRaises(AccessError):
            booking.with_user(self.employee).write({'name': 'Not mine'})
    # --------- End test_employee_cannot_edit_someone_elses_booking ----------

    # The record rule also checks new bookings: Booked By must be the employee.
    # -------------- test_employee_cannot_book_for_someone_else --------------
    def test_employee_cannot_book_for_someone_else(self):
        with self.assertRaises(AccessError):
            self.env['booking.booking'].with_user(self.employee).create({
                'name': 'For someone else',
                'resource_id': self.room.id,
                'user_id': self.other_employee.id,
                'start': bangkok_to_utc(FUTURE_DAY, 9),
                'stop': bangkok_to_utc(FUTURE_DAY, 10),
            })
    # ------------ End test_employee_cannot_book_for_someone_else ------------

    # ir.model.access.csv gives employees no delete right; they cancel instead.
    # ---------------- test_employee_cannot_delete_a_booking -----------------
    def test_employee_cannot_delete_a_booking(self):
        booking = self.book(self.employee, 9, 10)
        with self.assertRaises(AccessError):
            booking.with_user(self.employee).unlink()
    # -------------- End test_employee_cannot_delete_a_booking ---------------

    # Employees only read resources; managers create and edit them.
    # ---------------- test_employee_cannot_change_resources -----------------
    def test_employee_cannot_change_resources(self):
        with self.assertRaises(AccessError):
            self.env['booking.resource'].with_user(self.employee).create({'name': 'My room'})
    # -------------- End test_employee_cannot_change_resources ---------------

    # ======================== End R1 Access Control =========================

    # R2: two active (Requested or Confirmed) bookings of one resource cannot overlap.
    # ========================= R2 No Double Booking =========================

    # 09:30-10:30 overlaps 09:00-10:00 in the same room.
    # ----------------- test_overlapping_booking_is_rejected -----------------
    def test_overlapping_booking_is_rejected(self):
        self.book(self.employee, 9, 10)
        with self.assertRaises(ValidationError):
            self.book(self.other_employee, 9.5, 10.5)
    # --------------- End test_overlapping_booking_is_rejected ---------------

    # A Confirmed booking also holds its slot, and moving a booking (write) is checked too.
    # ----------- test_moving_onto_a_confirmed_booking_is_rejected -----------
    def test_moving_onto_a_confirmed_booking_is_rejected(self):
        first = self.book(self.employee, 9, 10)
        first.with_user(self.manager).action_confirm()
        second = self.book(self.other_employee, 11, 12)
        with self.assertRaises(ValidationError):
            self.move(second, self.other_employee, 9.5, 10.5)
    # --------- End test_moving_onto_a_confirmed_booking_is_rejected ---------

    # 10:00-11:00 right after 09:00-10:00 is not an overlap.
    # ---------------- test_back_to_back_bookings_are_allowed ----------------
    def test_back_to_back_bookings_are_allowed(self):
        self.book(self.employee, 9, 10)
        self.book(self.other_employee, 10, 11)
    # -------------- End test_back_to_back_bookings_are_allowed --------------

    # Only the same resource counts.
    # ------------ test_same_time_in_another_resource_is_allowed -------------
    def test_same_time_in_another_resource_is_allowed(self):
        other_room = self.env['booking.resource'].create({'name': 'Other Room'})
        self.book(self.employee, 9, 10)
        self.book(self.other_employee, 9, 10, resource=other_room)
    # ---------- End test_same_time_in_another_resource_is_allowed -----------

    # A cancelled booking no longer holds its slot.
    # ---------------- test_cancelled_booking_frees_its_slot -----------------
    def test_cancelled_booking_frees_its_slot(self):
        first = self.book(self.employee, 9, 10)
        first.with_user(self.employee).action_cancel()
        self.book(self.other_employee, 9, 10)
    # -------------- End test_cancelled_booking_frees_its_slot ---------------

    # A booking that ends before it starts is rejected.
    # --------------------- test_end_must_be_after_start ---------------------
    def test_end_must_be_after_start(self):
        with self.assertRaises(ValidationError):
            self.book(self.employee, 10, 9)
    # ------------------- End test_end_must_be_after_start -------------------

    # ======================= End R2 No Double Booking =======================

    # R3: bookings must fit the resource's opening hours, on one day, in Bangkok time.
    # =========================== R3 Opening Hours ===========================

    # Exactly 08:00-18:00 fits a room open 08:00-18:00.
    # ------------- test_booking_inside_opening_hours_is_allowed -------------
    def test_booking_inside_opening_hours_is_allowed(self):
        self.book(self.employee, 8, 18)
    # ----------- End test_booking_inside_opening_hours_is_allowed -----------

    # Starting before opening or ending after closing is rejected.
    # ------------ test_booking_outside_opening_hours_is_rejected ------------
    def test_booking_outside_opening_hours_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.book(self.employee, 7, 9)
        with self.assertRaises(ValidationError):
            self.book(self.employee, 17, 19)
    # ---------- End test_booking_outside_opening_hours_is_rejected ----------

    # The opening hours are checked again when a booking is moved.
    # ------------ test_moving_outside_opening_hours_is_rejected -------------
    def test_moving_outside_opening_hours_is_rejected(self):
        booking = self.book(self.employee, 9, 10)
        with self.assertRaises(ValidationError):
            self.move(booking, self.employee, 17, 19)
    # ---------- End test_moving_outside_opening_hours_is_rejected -----------

    # A booking must end on the day it starts, even in a room open 00:00-24:00.
    # ---------------- test_booking_past_midnight_is_rejected ----------------
    def test_booking_past_midnight_is_rejected(self):
        open_all_day = self.env['booking.resource'].create({
            'name': 'Open all day', 'open_from': 0, 'open_to': 24,
        })
        with self.assertRaises(ValidationError):
            self.book(self.employee, 22, 1, end_day=FUTURE_DAY + datetime.timedelta(days=1),
                      resource=open_all_day)
    # -------------- End test_booking_past_midnight_is_rejected --------------

    # A resource cannot close before it opens.
    # ------------------ test_opening_hours_must_make_sense ------------------
    def test_opening_hours_must_make_sense(self):
        with self.assertRaises(ValidationError):
            self.env['booking.resource'].create({
                'name': 'Bad hours', 'open_from': 18, 'open_to': 8,
            })
    # ---------------- End test_opening_hours_must_make_sense ----------------

    # ========================= End R3 Opening Hours =========================

    # R4: the status moves only along the allowed path, by the right person.
    # ============================= R4 Lifecycle =============================

    # create() ignores a status sent with the values.
    # ------------- test_new_booking_always_starts_as_requested --------------
    def test_new_booking_always_starts_as_requested(self):
        booking = self.env['booking.booking'].with_user(self.manager).create({
            'name': 'Sneaky',
            'resource_id': self.room.id,
            'start': bangkok_to_utc(FUTURE_DAY, 9),
            'stop': bangkok_to_utc(FUTURE_DAY, 10),
            'state': 'confirmed',
        })
        self.assertEqual(booking.state, 'requested')
    # ----------- End test_new_booking_always_starts_as_requested ------------

    # The Confirm button moves Requested to Confirmed for a manager.
    # ------------------- test_manager_confirms_a_booking --------------------
    def test_manager_confirms_a_booking(self):
        booking = self.book(self.employee, 9, 10)
        booking.with_user(self.manager).action_confirm()
        self.assertEqual(booking.state, 'confirmed')
    # ----------------- End test_manager_confirms_a_booking ------------------

    # Only a Manager may confirm, even their own booking.
    # --------------------- test_employee_cannot_confirm ---------------------
    def test_employee_cannot_confirm(self):
        booking = self.book(self.employee, 9, 10)
        with self.assertRaises(UserError):
            booking.with_user(self.employee).action_confirm()
    # ------------------- End test_employee_cannot_confirm -------------------

    # Requested cannot jump to Completed, and Cancelled is final.
    # -------------------- test_status_cannot_skip_a_step --------------------
    def test_status_cannot_skip_a_step(self):
        booking = self.book(self.employee, 9, 10)
        with self.assertRaises(UserError):
            booking.with_user(self.manager).write({'state': 'completed'})
        booking.with_user(self.manager).action_cancel()
        with self.assertRaises(UserError):
            booking.with_user(self.manager).action_confirm()
    # ------------------ End test_status_cannot_skip_a_step ------------------

    # There is no way back from Confirmed to Requested.
    # ---------------- test_confirmed_booking_cannot_go_back -----------------
    def test_confirmed_booking_cannot_go_back(self):
        booking = self.book(self.employee, 9, 10)
        booking.with_user(self.manager).action_confirm()
        with self.assertRaises(UserError):
            booking.with_user(self.manager).write({'state': 'requested'})
    # -------------- End test_confirmed_booking_cannot_go_back ---------------

    # The owner may cancel their own booking.
    # -------------------- test_owner_cancels_own_booking --------------------
    def test_owner_cancels_own_booking(self):
        booking = self.book(self.employee, 9, 10)
        booking.with_user(self.employee).action_cancel()
        self.assertEqual(booking.state, 'cancelled')
    # ------------------ End test_owner_cancels_own_booking ------------------

    # While a booking is Requested, the owner may still move it.
    # --------------- test_employee_moves_a_requested_booking ----------------
    def test_employee_moves_a_requested_booking(self):
        booking = self.book(self.employee, 9, 10)
        self.move(booking, self.employee, 11, 12)
        self.assertEqual(booking.start, bangkok_to_utc(FUTURE_DAY, 11))
    # ------------- End test_employee_moves_a_requested_booking --------------

    # After a manager confirms, the owner cannot move it any more.
    # ------------ test_employee_cannot_move_a_confirmed_booking -------------
    def test_employee_cannot_move_a_confirmed_booking(self):
        booking = self.book(self.employee, 9, 10)
        booking.with_user(self.manager).action_confirm()
        with self.assertRaises(UserError):
            self.move(booking, self.employee, 11, 12)
    # ---------- End test_employee_cannot_move_a_confirmed_booking -----------

    # A manager may still move a confirmed booking.
    # ---------------- test_manager_moves_a_confirmed_booking ----------------
    def test_manager_moves_a_confirmed_booking(self):
        booking = self.book(self.employee, 9, 10)
        booking.with_user(self.manager).action_confirm()
        self.move(booking, self.manager, 11, 12)
        self.assertEqual(booking.start, bangkok_to_utc(FUTURE_DAY, 11))
    # -------------- End test_manager_moves_a_confirmed_booking --------------

    # An employee can never change Booked By.
    # --------------- test_employee_cannot_give_a_booking_away ---------------
    def test_employee_cannot_give_a_booking_away(self):
        booking = self.book(self.employee, 9, 10)
        with self.assertRaises(UserError):
            booking.with_user(self.employee).write({'user_id': self.other_employee.id})
    # ------------- End test_employee_cannot_give_a_booking_away -------------

    # =========================== End R4 Lifecycle ===========================
