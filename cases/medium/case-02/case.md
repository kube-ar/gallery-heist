# case-02: Lanterns on the Canal

On the night of 2026-07-08, the Verrin Museum of Art held its gala. At 23:45 a guard
on a round found an empty frame in the Portrait Gallery (east wing):
*Lanterns on the Canal* by Mirela Danescu (1929) was gone. A guard's round at 22:12
had found it in place.

The museum's systems exported everything they recorded that night. They don't share ids:
each system knows people by its own.

| Folder | System | What it holds |
|---|---|---|
| `hr/` | Human resources | Staff, with employee ids and phones |
| `events/` | Events team | Guests, who invited them, the dinner seating |
| `vendors/` | Procurement | Contract workers and their companies |
| `security/` | Security | Badges, doors, the keycard log, cameras and their log |
| `facilities/` | Facilities | Rooms and wings |
| `telecom/` | Phone company | Calls between numbers, the night and the weeks before |
| `finance/` | Bank | Accounts and transfers in the weeks before |

Times are local, `YYYY-MM-DDTHH:MM`. The gala night runs past midnight.
