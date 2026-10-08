# Domain model

## Schedules vs assignments

A **schedule** describes when a duty exists and how its initial assignee is chosen. An **assignment** is the actual duty on a concrete date. Once an assignment exists, it is not recalculated from the schedule.

This distinction is intentional: editing a rotation must not retroactively change an already published month.

## Seeded schedules

Seeded names are Portuguese (`Noite`, `Almoço - Sábados`, `Almoço - Domingo`); the slugs stay `night`, `saturday-lunch` and `sunday-lunch`.
Each schedule carries `start_time`/`end_time`, the hours the shift runs, editable by an administrator on its configuration page: `20:30–00:00` for the night and `13:00–16:00` for both lunches. An end at or before the start means the shift runs into the next day.

## Backups

Every start copies the SQLite file aside before anything else runs, using SQLite's own backup API so the copy is consistent. Files go to `backups/` next to the database (or `BACKUP_DIR`), are named `rota-YYYYmmdd-HHMMSS.db` and are never overwritten: two starts in the same second increment the name. Nothing is copied for another engine or an in-memory database, and a failed backup only logs a warning instead of stopping the app. Nothing is ever pruned, so the folder grows one file per start.

## Calendar feeds

- `/calendar/<token>.ics` is an iCalendar feed anybody can subscribe to from Google Calendar, Apple Calendar or Outlook. Every team has its own token, created the first time someone assigned to it opens `/calendar`, and its feed only carries the shifts assigned to it.
- `/calendar` is the page holding those links: the rota only has a button pointing there, so it keeps showing nothing but who works each day. A user gets one feed per active team it is assigned to, each titled `Turnos de <equipa>`, plus the whole-rota feed for administrators. Each feed has mobile-sized **iPhone / Apple Calendar**, **Google Calendar / Android**, and **Outlook** actions. Apple opens a `webcal://` subscription; Google and Outlook open web subscription flows with the feed address encoded in the link. The page includes platform-specific instructions, a readonly address field, and **Copiar endereço**, with clipboard-error handling and a native-selection fallback for phones.
- Google does not add URL subscriptions through its mobile app: use its desktop web interface (request the desktop site on the phone, or use a computer), then enable the calendar in the mobile app using the same account. Outlook subscriptions also use its web interface. Subscriptions refresh according to the provider's schedule, rather than instantly; Google and Outlook must be able to fetch the address over the Internet. Importing a downloaded `.ics` file is a snapshot and is not the subscription workflow.
- Administrators also get one shared feed with the whole rota, using the team token in `CALENDAR_TOKEN` (generated on first use and shown on `/admin/schedules`).
- A feed publishes one month back and six months forward. Times carry the bar's timezone (`DTSTART;TZID=Europe/Lisbon:20261017T203000`) and the feed declares it in `X-WR-TIMEZONE` plus a `VTIMEZONE` block with the European summer-time rules (WET/WEST), so every client shows a night at 20:30 and keeps the right offset across the year. The zone comes from `TIMEZONE`; an unknown zone falls back to `Europe/Lisbon`. Times and names are private member data: the token is the only protection, so the shared link goes only to the team.
- Each event title is `<equipa> · <escala> · <horas>` so a list of shifts reads at a glance; a shift without a team keeps `<escala> · <horas>`.
- An unknown token returns 404, and a deactivated team's token stops working.

### Night (`Noite`)

- Exists every day (`Monday` through `Sunday`).
- Type: `fixed`.
- Configured once as a repeating monthly pattern: one team per calendar day of the month (1 to 31), configured on `/admin/schedules/<night id>`.
- Generation fills a missing assignment with the team configured for that day of the month. Days 29 to 31 only apply to months that have them.
- There is no per-month configuration for Night: the same pattern is used every month.
- Existing assignments are never rewritten by a pattern change; they keep the team they already had.
- An administrator can explicitly **Aplicar padrão** from a chosen month and year on `/admin/schedules/<night id>`. It rewrites every existing `generated` night from the first day of that month onwards, in that month and every later one, to match the current pattern. It is the explicit way to push a corrected pattern onto shifts that already have a team. Assignment IDs, notes and completed request history are kept, `manual` assignments and completed swaps are preserved, days with nobody in the pattern are left as they are, and no assignment is ever created. Open and pending change requests on a rewritten shift are cancelled and the new and previous teams are notified.

### Saturday Lunch (`Almoço - Sábados`)

- Saturdays only.
- Type: `rotation`.
- Has its own ordered member list.
- Continues after the previously assigned team's position in the rotation, including across month boundaries. The anchor date is the fallback when there is no usable previous assignee.

### Sunday Lunch (`Almoço - Domingo`)

- Sundays only.
- Type: `rotation`.
- Has its own ordered member list, independent of Saturday.

The data model supports a schedule matching multiple weekdays even though the seeded lunch schedules each use one day.

## Rotation generation

For a rotation schedule, use the last assigned team on an earlier date in that same schedule as the reference. Choose the next active member after that team's position in the current rotation order, wrapping to the beginning. Unassigned dates are skipped when finding the reference. Manual assignments and completed swaps also supply the reference for later dates. Saturday and Sunday never use each other's assignees.

Inactive teams are skipped as recipients, but their position can still supply the reference if they remain in the rotation. When no previous assignee exists, or that team has been removed from the rotation, fall back to the number of matching schedule days from the anchor date modulo the active member count. An empty active rotation leaves the shift unassigned.

Generation and explicit month/range application process dates chronologically, so each newly assigned date supplies the reference for the next date. Regenerating one assignment only recalculates that date; later existing assignments remain unchanged until an administrator explicitly applies the rotation.

Only missing assignments are generated. Existing rows are never rewritten.

An administrator can explicitly **Apply rotation** on a lunch schedule's month page. This recalculates that month's `generated` assignments using the current active rotation members and fills missing dates for that schedule. Manual assignments and completed swaps are preserved. Simply editing the rotation order still does not rewrite any assignment.

Every assignment on a lunch schedule page has a **Regenerate** button. An administrator can explicitly regenerate any assignment, including an automatic assignment, manual override, or completed swap. It immediately recalculates that date from the current rotation and its source becomes `generated`; if there are no active rotation members, it becomes unassigned. These actions preserve assignment IDs, notes, and completed request history. If ownership changes, open or pending-approval change requests for the assignment are cancelled, and assignment-change notifications are attempted after saving.



**Limpar turnos** empties the `generated` shifts of a lunch schedule from the first day of a chosen month and year onwards, in that month and every later one, so they read as unassigned. No shift is deleted: rows keep their IDs, notes, source and completed request history, and stay `generated`, so **Aplicar rotação** fills them again. Manual assignments and completed swaps are never emptied. Open and pending change requests on an emptied shift are cancelled and the previous team is notified. Use it to force a recalculation from a known point instead of relying on the shifts that already exist.

## Teams and users

- A **team** (`teams`) is who works a shift: one person, or the people who cover it together. Every rota row, rotation position, pattern day and change request names a team.
- A **user** (`users`) is a login: a username, a password, a label, the administrator flag, the e-mail every notification is sent to and the per-user opt-in for them. A team points at one user through `teams.user_id`, and a team without one is rota-only: nobody signs in for it.
- `phone` belongs to the team; `email` and the e-mail opt-in belong to the user. A rota-only team has nobody to write to.
- The two are created on separate pages, and neither page creates the other:
  - `/admin/teams` adds and edits teams (name, phone, active) and only *selects* which user signs in for each one. There are no usernames, passwords or e-mails on this page.
  - `/admin/users` creates and edits users (name, username, password, e-mail, notifications opt-in, administrator, active) and assigns each of them to the teams it signs in for. There are no team names or contacts on this page.
- One user can be assigned to several teams, which is how a team shares a single login, and the same username can never belong to two users. Ticking a team on `/admin/users` assigns it to that user and takes it away from whoever had it; the teams page is where a team is simply pointed at one user.
- Administration is a property of the **user**, so a team covered by an administrator user is administrated by whoever signs in with it.
- Rota-only teams can be assigned by an administrator, appear in rotations, and can be named as the target of a change request, but cannot answer it; an administrator completes the transfer on the schedule's own configuration page.
- Any password of at least four characters is accepted; there is no complexity rule.
- The session stores the user, never a team. Everything a member sees and does is scoped to the teams assigned to it: their shifts are the "mine" ones on the rota, their change requests are the ones listed, its calendar page holds one feed per team, and it can open and answer requests for any of them. A request made by one of those teams is its own: nobody can accept it through the same user, and a swap naming a team of the same user is refused.
- When a user accepts a request, the rota still records one team: the one the request names, or the user's first active team when the request names nobody. Ownership rules are checked against that team.
- A signed-in user reaches its account through the top bar, which opens `/account`: a single field for the new password, with no confirmation and no retyping of the current one, so anyone holding an open session can change it, and a second panel where it keeps its own notification e-mail and the opt-in. The page lists the teams the user signs in for.
- A user cannot be deactivated, demoted or removed while it is the last one that can sign in as an administrator, and nobody can deactivate or remove the user they are signed in with.
- A team cannot be deactivated or lose its user while it is the only team of the user you are signed in with.
- An administrator can remove a team permanently from `/admin/teams`, after a confirmation page that lists the impact. A team that still holds any assignment, past ones included, cannot be removed: those shifts must first be handed over, so the record of who worked each date stays intact. SQLite cascades are not enforced by the application, so the removal clears the remaining references explicitly: night-pattern days lose their team, rotation positions are deleted, that team's own change requests are deleted and the ones that merely targeted or were accepted by them lose those references, and notification logs keep their history without the team.
- Nobody may remove their own team or the team of the last remaining administrator. The teams page only shows the remove button for the teams that pass these checks; the endpoints enforce them again. Deactivating is the non-destructive alternative.
- A user is removed from `/admin/users` only once no team is assigned to it.

## Access

### PDF export

- Administrators use the **Exportar PDF** controls directly on `/admin/schedules`.
  Each schedule card links to those controls with that schedule selected. Other
  signed-in users can open `/export/schedule`. Both forms select one active
  schedule and exact start/end dates, both inclusive (up to 12 calendar months).
- `/export/schedule.pdf` downloads an A4 PDF directly. It lists day numbers and
  teams under Portuguese month headings, with the CRR logo. Font size and columns
  adapt to keep the selected range on one page; long names wrap without truncation.
- Generation fills missing assignments in chronological order using the ordinary
  monthly generator. Existing assignments, including manual overrides and swaps,
  keep their current owners. Only rows for the selected schedule and dates appear
  in the PDF.

### Page access

- `/` is the rota and is the landing page for everyone, signed in or not. Signed-out visitors see the month read-only: no "mine" highlighting, no change-request actions.
- `/admin/schedules` is the hub of the schedules and the only place that lists them: each card shows its kind and hours, the next dates of a rotation, its rotation order or the night pattern, and links to its configuration page. Signed-out visitors have no navigation at all; the brand logo is the way back to the rota.
- Change requests, `/swaps`, and every `/admin` page still require a signed-in, active user.
- Internal links are built with `settings.url()` (exposed to templates as `app_path`) and redirects go through the same helper, so `ROOT_PATH` keeps every link working under a proxy sub-path.

## Change request state machine

`open` → `pending_approval` → `approved`

Other terminal states: `rejected`, `cancelled`, `reverted`.

- A swap is always **one shift for one shift**: it is created on `/swaps/new` (its own page, so the rota keeps showing only who works each day) and names both shifts. The team giving the first shift is the requester; the team owning the second one is the target. There are no open offers.
- The two shifts must belong to the same schedule. The teams of a schedule are the ones in its rotation, in its monthly pattern, or already holding one of its shifts.
- When a swap is approved or accepted, **both** assignments change hands at once: the target takes the requester's shift and the requester takes the target's shift. Both become `swap` and the users signing in for both teams are notified.
- One team can work several days in a month, so each side of the exchange is chosen from a list of the month's future shifts, grouped by schedule: the requester picks "O turno que passo" (their own shifts) and "O turno que quero em troca" (another team's shifts of that schedule). A member only sees the shifts of the teams their user is assigned to on the first list; an administrator sees all of them.
- A shift can only be part of one open request at a time, on either side.
- An administrator can open a request for another team's shift. The request is still recorded against the team that owns the shift, so the ownership rule below keeps working; unassigned and past shifts cannot be requested.
- `/admin/assign` is the day-by-day picker for administrators: pick a day, then put a team on one of its shifts with **Atribuir**. This is a direct assignment, never a change request. It sets the assignment source to `manual`, cancels any open request that involves that shift, and notifies the users signing in for the new and the previous team. `Sem atribuição` clears it. The date must match one of the schedule's weekdays.
- The requester cannot accept their own request. With a user covering several teams, that covers every one of them.
- Only the team the request names can accept it or decline it, and with a user covering several teams that means the user the named team is assigned to.
- If the schedule requires manager approval, acceptance moves to `pending_approval`.
- Nobody can decline their own request; the requester cancels it instead. An administrator may decline any `open` or `pending_approval` request.
- An administrator can approve a `pending_approval` request (it goes to whoever accepted it) or an `open` one, choosing another team of the same schedule when there is no named partner. Approval and decline are available both in `/swaps` and on the rota page next to the shift.
- Approval transfers the assignment and sets its source to `swap`.
- Only an administrator can revert an approved two-sided swap: both shifts go back to the teams that had them, their source becomes `manual` (the original source cannot be recovered) and a note records the revert. If either shift changed after the swap, the revert is refused and the day-by-day assignment must be used instead.
- If either team no longer owns its own shift, the request must not be applied and is cancelled.
- On a schedule's configuration page, an administrator can complete an `open` or `pending_approval` request on a team's behalf by choosing another team that works that same schedule. This is the only way a rota-only team gives up or receives a shift. The same ownership rule applies, other open requests for that assignment are cancelled, and the users signing in for the requester and the new team are both notified. Past dates are refused.

## Notifications

Email is optional per user and per installation.

One user covering several teams receives each notification once, addressed to its
own e-mail, and the notification log keeps both the user and the team the event
concerned.

Events include:
- assignment updated/removed by admin;
- change requested;
- change accepted;
- manager approval required;
- change approved/rejected;
- shift reminder.

An email error is logged but must not undo a scheduling action.
