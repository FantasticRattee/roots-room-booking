# Room Booking (Odoo module)

A room and equipment booking module for Odoo 18. People book a room, a piece of equipment, or both together, for a time slot. A Manager confirms the request, and the system blocks double bookings, bookings outside opening hours and status changes that skip a step.

## Run it locally

You need [Docker Desktop](https://www.docker.com/products/docker-desktop/).

```bash
docker compose up -d
```

The first time only (and again after `docker compose down -v`), create the database and install the module:

```bash
docker compose run --rm odoo odoo -d booking -i base --stop-after-init
docker compose run --rm odoo odoo -d booking -i room_booking --stop-after-init
docker compose restart odoo
```

Then open http://localhost:8069 and log in with `admin` / `admin` (Odoo's default for a new local database). The admin user is a Manager from install. Open the **Room Booking** app.

To try the employee rules, create a second user in **Settings > Users** as an Internal User, leave the **Room Booking** field empty (empty = Employee), set a password, and log in as that user in a private window.

## Work on the module

The module lives in `addons/room_booking`. The `addons` folder is shared with the Odoo container, so there is nothing to rebuild. The running Odoo server does not load changes by itself: after each change, upgrade the module and restart Odoo.

```bash
docker compose run --rm odoo odoo -d booking -u room_booking --stop-after-init
docker compose restart odoo
```

One exception: the sample resources (`data/booking_resource_data.xml`) are `noupdate`, so an upgrade does not reapply edits to them. Change them in the app or start from an empty database.

Run the module's tests (the module must be installed):

```bash
docker compose run --rm odoo odoo -d booking -u room_booking --test-enable --test-tags /room_booking --stop-after-init
docker compose restart odoo
```

Near the end of the log, look for the line `odoo.tests.result: 0 failed, 0 error(s) of 30 tests`. (The `odoo.tests.stats` line just above it shows a slightly higher count; the result line is the one that counts.) If the number of tests is 0, no test ran (usually because the module is not installed yet), so it is not a pass. Each test runs in a transaction that is rolled back, so the tests do not change the data.

Other commands:

```bash
docker compose logs -f odoo    # see the server log
docker compose down            # stop everything (the data is kept)
docker compose down -v         # start again from an empty database (deletes all data)
```

## What the module does

The code comments and the test groups refer to the requirements by these IDs.

| ID | Requirement | How it works | Where |
|---|---|---|---|
| R1 | CRUD with access control | Two groups. **Employee** (Odoo's Internal User group, `base.group_user`) reads all bookings, creates and edits only their own, and cannot delete (they cancel instead). **Manager** (added by this module) does everything and manages resources. In the Users form, the Room Booking field blank = Employee and "Manager (all bookings)" = Manager. | `security/` |
| R2 | Conflict prevention | A booking is **rejected** when another Requested or Confirmed booking of the same resource overlaps it. Two slots overlap when each starts before the other ends, so 10:00–11:00 and 11:00–12:00 are fine. | `_check_no_double_booking` |
| R3 | Availability windows | Each resource has opening hours (`Open From` / `Open To`, default 08:00–18:00). A booking must start and end inside them, on the same day, in office time (Asia/Bangkok). | `_check_inside_opening_hours`, `_check_opening_hours_are_valid` |
| R4 | Lifecycle | Requested → Confirmed → Completed, and Requested or Confirmed → Cancelled. Completed and Cancelled are final. A new booking always starts as Requested. Only a Manager confirms. The owner or a Manager cancels. | `create()`, `write()`, Confirm / Cancel buttons |
| R5 | Views | List view first, then calendar (one colour per resource) and form. Search filters: My Bookings, To Approve, group by Resource, Rooms, Equipment. Menus: Bookings, Rooms, Equipment, and Configuration (Managers only). | `views/` |

The brief also lists three additional rules (use a core Odoo module, an AI feature, scheduled automation). I did not build any of them in this version. I kept the module to the base features so that every line is one I can explain.

## Design decisions and trade-offs

- **Reject, not flag.** A double booking is never saved, so the data can always be trusted. The error message names the booking that is in the way. Flagging would let both people believe they have the room.
- **Rules live on the server.** Data rules are `@api.constrains` methods. Who may change the status, and when, is checked in `write()`. Every way into the data (the form, the list, import, the API) goes through them. The buttons and their `groups` / `invisible` attributes only hide what a user cannot use; they do not protect anything.
- **Employees may change the slot only while Requested.** An employee can never give a booking to someone else. After a Manager confirms it, they also cannot move it or change its resource; they cancel it and book again. A Manager can still edit it.
- **Concurrent saves.** The overlap check runs in Python. If two people save overlapping bookings at the same moment, each request reads the database before the other has committed, so both can pass. A database rule would close this gap: a PostgreSQL `EXCLUDE` constraint on the resource and the time range (with the `btree_gist` extension), limited to Requested and Confirmed bookings. I left it out to keep the module basic. For a busy production system I would add it.
- **One opening window per day, fixed time zone.** Every resource has one window, the same every day, in Bangkok time. There are no weekend or holiday closures. Changing a resource's hours does not re-check bookings that already exist.
- **Duplicate.** Duplicating a booking that still holds its slot fails, because the copy has the same resource and time, which is a double booking. Duplicating a cancelled or completed booking works.
- **Room and equipment in one save.** The form has a Room field and an Equipment field. If both are filled, one save makes two bookings, one per resource, with the same purpose, owner and time. If the equipment is already taken, neither booking is saved. Each booking is still checked on its own resource (overlap and opening hours). The two bookings are separate records: cancelling one does not cancel the other, and moving one does not move the other. One booking with several resources would change every rule, so I left it out to keep the module basic.
- **Sample data.** Three sample resources are loaded as normal data, not demo data, because this setup runs without demo data. Delete them in a real database.

## Project layout

```
addons/room_booking/
├── __manifest__.py
├── models/
│   ├── booking_resource.py     resource + opening hours check
│   └── booking_booking.py      booking: fields, rules, lifecycle, buttons
├── security/                   groups, record rules, access rights
├── views/                      list, form, calendar, search, menus
├── data/                       sample resources
└── tests/test_booking.py       30 tests, grouped by rule (R1–R4, room and equipment)
docs/                           design and diagrams (open the HTML files in a browser)
```
