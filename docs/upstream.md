# Upstream synchronisation

Vitriolic can mirror the draws and results that a sporting body publishes on
a hosted competition management platform -- the *upstream provider* -- into a
`Season`. The provider is authoritative for everything it manages: each
synchronisation fetches a complete snapshot of the remote competitions and
converges the local divisions, pools, teams, fixtures and results onto it.

Two providers are supported, each described in its own document:

| Provider | Used by | Remote interface | Document |
| --- | --- | --- | --- |
| MySideline | Touch Football Australia and other NRL community sports | anonymous GraphQL API plus a server-rendered listing | [mysideline.md](mysideline.md) |
| revolutioniseSPORT | hockey, water polo, squash and other associations | HTML pages, scraped | [revolutionise.md](revolutionise.md) |

This document covers what is common to both: how a season is linked, how
records are identified, how names are handled and what a synchronisation
does. Division and team names are the one thing a provider is not
authoritative for; see [Naming](#naming).

## Configuration

A competition belongs to exactly one provider, and its seasons each name the
page on that provider listing their draws:

1. On the competition edit form set **Upstream URL** to the organisation's
   page on the provider: the MySideline association page
   (`https://tfa.mysideline.com.au/competitions/association/299999`) or the
   revolutioniseSPORT organisation's draws index
   (`https://www.revolutionise.com.au/ccha/games`). The URL is validated and
   normalised; the provider is recognised from the host.
2. On each season set **Upstream URL** to the page on the same provider that
   lists exactly that season's draws, which is what the provider's own site
   shows when you narrow it down: on MySideline the association page with
   the *Year* (and optionally period) drop-down applied
   (`.../association/299999?season=2025&seasonTag=2`); on revolutioniseSPORT a
   competition's draws page (`https://www.revolutionise.com.au/ccha/games/25527`)
   or the index itself to take every competition the organisation currently
   publishes. The URL must belong to the organisation the competition names.

A season without an upstream URL is never synchronised.
`Season.upstream_enabled` reports whether both URLs are set and
`Season.upstream_provider` (also on `Competition`) names the provider.

Both URLs are also exposed by the MCP administration tools
(`create_competition`, `update_competition`, `create_season`, `update_season`).

## Invocation

* **Admin**: linked seasons show a button named after the provider in the
  season list which leads to the *Synchronise with …* page and queues a
  synchronisation.
* **Celery**: `tournamentcontrol.competition.tasks.synchronise_upstream`
  synchronises every enabled, incomplete linked season, isolating failures
  per season; `synchronise_upstream_season(season_pk)` does one. Schedule
  the former with Celery beat in the deploying project, eg. every 15
  minutes on match days.
* **Management command**: `synchronise_upstream [season_pk ...]`.
* **Python**: `tournamentcontrol.competition.upstream.sync.synchronise_season`.

## Identifiers

Every division, team and match a provider manages carries an `upstream_id`:
the provider's own identifier qualified by the provider's key, for example
`mysideline:69295321` for a MySideline competition or `revolutionise:2433163`
for a revolutioniseSPORT game. The value is unique across providers, says
where a record came from without a foreign key to anything, and is the key
the synchronisation matches on, so renames upstream keep local relations
(matches, registrations, ladders) intact. It is set by the synchronisation,
never by hand; a record that has one is managed by the provider, one that
does not is native and is never touched.

The fields are provided by `UpstreamIdentifierMixin` (`Match`) and
`UpstreamMixin` (`Division`, `Team`, which also keep the upstream name).
`upstream_provider` on any of them resolves the provider from the prefix.

### Code layout

```
tournamentcontrol/competition/upstream/
    base.py          errors, HTTP transport, the UpstreamProvider interface
    types.py         provider-neutral snapshot types (RemoteCompetition, ...)
    sync.py          the reconciler
    mysideline.py    the MySideline provider
    revolutionise.py the revolutioniseSPORT provider
    __init__.py      the registry: provider_for_url, provider_for_identifier
```

Adding a provider means adding one module implementing `UpstreamProvider`
(URL recognition and canonicalisation, a client, and `fetch_snapshot`
returning `RemoteCompetition` objects) and listing it in `PROVIDERS`. Nothing
in the models, forms, admin or reconciler names a provider.

## Mapping onto Vitriolic

| Snapshot | Vitriolic |
| --- | --- |
| organisation | `Competition` (`upstream_url`) |
| season page | `Season` (`upstream_url`) |
| competition | `Division` (`upstream_id`); title and slug follow the remote name unless it has been changed locally (see [Naming](#naming)) |
| `Regular` rounds | `Stage` "Regular Season" |
| `Final` rounds | `Stage` "Finals" with `keep_ladder` off (created only when finals fixtures exist; `Match.label` carries the round's name, eg. "Grand Final") |
| pool | `StageGroup` on the regular stage; `Team.stage_group` and, for intra-pool matches, `Match.stage_group` |
| team | `Team` (`upstream_id`); title and slug follow the remote name unless it has been changed locally |
| match | `Match` (`upstream_id`): round number, date/time in the venue's time zone (falling back to the season's), `play_at`, teams, scores, bye, forfeit |
| venue / field | `Venue` (matched by title within the season, created with the venue's coordinates and time zone when absent) and `Ground` ("Field *n*" for a numeric field, otherwise the field's name; created when absent) |
| participant to be advised | `UndecidedTeam` labelled "TBA" on the stage |

A division is created with a points formula from the provider's ladder
template when one is available (MySideline publishes one per competition;
revolutioniseSPORT's is inferred from the ladder totals), or the TFA standard
ladder (`3*win + 2*draw + 1*loss + 3*bye + 3*forfeit_for`) otherwise; the
forfeit score defaults from the template too. Ladder configuration is not
overwritten by later syncs and may be changed freely. When defaults were
applied the synchronisation says so in its warnings. A division or team
created by hand with the same title as a remote one is *adopted* (linked) on
the first synchronisation rather than duplicated, so ladder settings can be
prepared before linking a season.

## Naming

The provider is authoritative for everything *except* the names of divisions
and teams. Upstream naming is frequently unwieldy -- Central Coast Touch
publishes a division on MySideline as "Born 2014 & 2013 u14 Boys" where "14
Boys" is what should appear on the website -- so the `title` of a linked
`Division` or `Team` may be edited in the admin and the synchronisation will
keep it.

Because the local name may be ours or theirs, and either side can change it
without telling the other, two copies of the remote name are kept beside our
own (both non-editable, set only by the synchronisation and the admin form):

| Field | Meaning |
| --- | --- |
| `title` | the name we publish |
| `upstream_title` | what the provider calls the record right now, refreshed on every synchronisation whether or not we use it |
| `upstream_title_synced` | what the provider called it when `title` was last reconciled with it: when the record was linked, when a remote rename was last applied, or when an administrator last saved it |

From these, `upstream_title_overridden` (`title != upstream_title_synced`) is
*our* variation and `upstream_title_changed`
(`upstream_title != upstream_title_synced`) is *theirs*. The synchronisation
then:

* applies the remote name while the record has no local variation -- the
  default, so nothing needs configuring for divisions whose upstream names
  are fine;
* keeps the local name when there is one, and **reports** an upstream rename
  of such a record (in `SyncResult.warnings`, the task log, the management
  command output and the *Synchronise with …* admin page) so that somebody
  can decide which name is right. The record is never silently renamed and
  the upstream change is never silently discarded.

An administrator resolves a reported rename by editing the division or team:
the form shows what the provider calls it and offers **Use the <provider>
name**, which discards the local name (and reverts the slug) so that later
renames are applied automatically again. Saving the form without ticking it
keeps the local name and acknowledges the remote change, so it is not
reported again until the provider renames the record once more. Records
awaiting that decision are listed on the *Synchronise with …* page for the
season.

`upstream_renamed(queryset)` filters divisions or teams to those awaiting a
decision.

Pools have no remote identifier -- they are matched by name -- so a pool
cannot be renamed locally; a local rename is treated as a new pool.

## Synchronisation semantics

The whole snapshot is fetched before anything is written, then applied
inside one transaction:

* **added** remotely: created locally (division, stage, pool, team, match,
  venue, ground as needed);
* **modified** remotely (date/time, field, teams, pool membership, bye):
  the corresponding fields are updated in place;
* **renamed** remotely: the local title and slug are updated unless the name
  has been changed locally (see [Naming](#naming)); identity is the
  `upstream_id` so relations (matches, registrations, ladders) are kept.
  Slugs marked as locked are left alone. A rename which would collide with
  another division in the season, or another team in the division, is
  reported and retried on the next synchronisation rather than failing;
* **scored** remotely: the scores are applied and the ladder is recalculated
  through the normal `Match` save signals. A result that is later changed or
  withdrawn is changed or cleared. A forfeit sets `is_forfeit`,
  `forfeit_winner` and the division's forfeit scores;
* **removed** remotely: matches are deleted; teams are deleted once their
  upstream fixtures are gone, or detached (identifier cleared) when native
  matches or registrations reference them; pools and the finals stage are
  deleted once empty; a division is deleted when everything in it could be,
  otherwise it is kept, marked as *draft* and reported.

Only records carrying an `upstream_id` are ever changed or removed; native
divisions, teams and matches in the same season are untouched, and venues
and grounds are never removed.

A transport failure, HTTP error, API error or a response that does not have
the expected shape raises before the transaction starts, so a temporary
outage never empties a competition. A database error during the apply rolls
back the whole snapshot.

Because the season URL selects what belongs to the season, moving a
competition out of that selection upstream (re-tagging a MySideline
competition to another year, or un-publishing a revolutioniseSPORT
competition from the index when the season URL is the index) removes it
locally on the next synchronisation, subject to the protection of native
data above. Mark a season *complete* once it is over; complete seasons are
not synchronised by the periodic task.

## History

The MySideline integration (which replaced the SportingPulse scraper removed
in 2017) was the first provider and gave the fields their original
`mysideline_*` names. Migration `0065_upstream` adds the generic fields and
copies the MySideline link into them (`mysideline_id` 69295321 becomes
`upstream_id` `mysideline:69295321`; a season's year and period become the
filtered association URL), and `0066_remove_mysideline` drops the old
columns.

## Test data

`tournamentcontrol/competition/tests/upstream.py` provides the in-memory
`requests.Session` stand-ins the unit and end-to-end tests drive the real
clients and reconciler with: `state_cup_session()` serves the captured NSW
State Cup 2025 from MySideline and `ccha_session()` the captured Central
Coast Hockey Association 2026 Mens competition from revolutioniseSPORT. Both
accept `renames={...}` to play back an upstream rename without a second
capture. See the provider documents for what was captured.
