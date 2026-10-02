# MySideline synchronisation

Vitriolic can mirror the competitions that Touch Football Australia publishes
on [MySideline](https://tfa.mysideline.com.au) into a `Season`. MySideline is
authoritative for everything it manages: each synchronisation fetches a
complete snapshot of the remote competitions and converges the local
divisions, pools, teams, fixtures and results onto it.

This replaces the SportingPulse scraper that was removed in 2017 (the
`Division.sportingpulse_url` field it left behind is dropped by migration
`0063_mysideline`). Division and team names are the one thing MySideline is
not authoritative for; see [Naming](#naming).

## Configuration

A MySideline *association* corresponds to a Vitriolic `Competition`, and each
"year" the association page lets you pick corresponds to a `Season`:

1. On the competition edit form set **MySideline URL** to the association
   page, for example
   `https://tfa.mysideline.com.au/competitions/association/299999` (NSW
   State Cup). The URL is validated and normalised; only the association id
   is used internally. Query parameters such as `?season=2025&seasonTag=2`
   copied from the site's filter link are accepted and dropped.
2. On each season set **MySideline season** to the year shown in the
   association page's *Year* drop-down (`season` in the remote data), eg.
   `2025`. Optionally set **MySideline season period** -- MySideline's
   `seasonTag`: `1` for the first half of the year (winter competitions),
   `2` for the second half (summer/spring) -- when one Vitriolic season
   should cover only part of a year.

A season without a MySideline season is never synchronised. `Season.mysideline_url`
gives the association page filtered to the season, which is what the site
itself produces from its drop-downs.

## Invocation

* **Admin**: linked seasons show a *MySideline* button in the season list
  which queues a synchronisation.
* **Celery**: `tournamentcontrol.competition.tasks.synchronise_mysideline`
  synchronises every enabled, incomplete linked season, isolating
  failures per season; `synchronise_mysideline_season(season_pk)` does one.
  Schedule the former with Celery beat in the deploying project, eg. every
  15 minutes on match days.
* **Management command**: `synchronise_mysideline [season_pk ...]`.
* **Python**: `tournamentcontrol.competition.mysideline.sync.synchronise_season`.

## Remote interface

The MySideline website is a Next.js application. It obtains its data from a
public, anonymous GraphQL API operated by the NRL:

    POST https://community-backend.api.nationalrugbyleague.io/graphql

No cookies, tokens or browser-generated headers are required; introspection
is enabled. The queries used are:

| Query | Purpose |
| --- | --- |
| `competitionMatches(competitionId)` | every fixture in a competition with round, date/time (epoch milliseconds, UTC), status, teams, scores, venue, field and forfeit/bye/TBA flags |
| `competitionLadder(competitionId)` | the team list with each team's `pool` name (the only place pool membership is exposed) |
| `teams(seasonId, nationalId, competitionId)` | the canonical team list for the competition |

The ladder points scheme of a competition (`laddertemplate`: points for a
win, draw, loss, bye and forfeit, and the default forfeit score) is likewise
not available per competition through GraphQL; it is read from the
competition page (`/competitions/<id>`) payload the same way. It only seeds
newly created divisions, so if that payload cannot be understood the sync
logs a warning and falls back to the TFA standard ladder rather than
failing.

There is no GraphQL query that lists competitions *by association*
(`competitions` is a text search over the whole national body). The
association page is server-rendered, so the listing is read from the React
Server Component payload the page embeds: requesting
`/competitions/association/<id>` with an `RSC: 1` header returns the payload
directly as `text/x-component`; the same payload is also present in the HTML
inside `self.__next_f.push([1, "..."])` script calls, which is used as a
fallback. The payload is a series of `<id>:<json>` lines; the listing is the
first JSON object containing a `competitions` array. Each entry carries
`_id`, `name`, `season`, `seasonTag` and `isActive`.

`nationalId` is derived from the host: `tfa.mysideline.com.au` is `TFA`.

### Identifiers and hierarchy

MySideline uses integer identifiers throughout, all stable across renames:

    association (6338)
      competition (69295321)       -> Division.mysideline_id
        team (69333380)            -> Team.mysideline_id
        pool ("Pool A", by name)   -> StageGroup (title)
        match (1388870728)         -> Match.mysideline_id
          round { number, type: Regular|Final, displayName }
          status: pre-game | final | forfeit
          venue { _id, name, venueTimezone }, meta.fieldNo

Pools have no identifier, only a name; they are matched by title.

### Observed behaviour and limitations

* The association page lists every competition the association has ever
  published; its *Year* / *Age* / period drop-downs are client-side filters
  mirrored into `?season=`, `?age=` and `?seasonTag=` query parameters, not
  separate requests.
* Match `status` values seen: `pre-game`, `final` (occasionally `Final` on
  byes; statuses are lower-cased), `forfeit`. Scores for a `pre-game` match
  are `0/0` and are ignored; only `final` supplies a result. `forfeit`
  carries `meta.forfeitingTeam`. Any other status is treated as unplayed so
  an unknown value never fabricates a result.
* Distinct competition or team names can slugify identically ("Men's 55s"
  and "Mens 55s"); slugs are suffixed (`-2`, ...) to keep them unique.
* A bye is a match with `meta.isBye` and one side empty. Finals whose
  participants are not yet known have `meta.isTba` and both sides empty;
  neither `competitionMatches` nor the full `match` query carries a
  placeholder such as "Winner QF1", so they are represented locally with a
  "TBA" undecided team until MySideline fills the teams in.
* `competitionLadder` only counts `Regular` rounds (a team with 5 pool
  matches and 3 finals shows `matchesPlayed: 5`), so the finals stage is
  created without a ladder. There is no per-competition flag for this; the
  competition-level `display.ladder` only controls whether the ladder is
  shown publicly.
* Matches do not say which pool they belong to; a match is attributed to a
  pool when both teams are in the same pool.
* The listing on the association page is not paginated. The GraphQL
  endpoints return complete lists; no pagination or rate limiting has been
  observed, and responses are served through CloudFront.
* The RSC payload format is an internal Next.js detail and is the most
  fragile part of the integration. If it changes, only the association
  listing is affected; competition data continues to come from GraphQL.

## Mapping onto Vitriolic

| MySideline | Vitriolic |
| --- | --- |
| association | `Competition` (`mysideline_url`) |
| year / period | `Season` (`mysideline_season`, `mysideline_season_tag`) |
| competition | `Division` (`mysideline_id`); title and slug follow the remote name unless it has been changed locally (see [Naming](#naming)) |
| `Regular` rounds | `Stage` "Regular Season" |
| `Final` rounds | `Stage` "Finals" with `keep_ladder` off (created only when finals fixtures exist; `Match.label` carries the round's display name, eg. "Grand Final") |
| pool | `StageGroup` on the regular stage; `Team.stage_group` and, for intra-pool matches, `Match.stage_group` |
| team | `Team` (`mysideline_id`); title and slug follow the remote name unless it has been changed locally (see [Naming](#naming)) |
| match | `Match` (`mysideline_id`): round number, date/time in the venue's timezone, `play_at`, teams, scores, bye, forfeit |
| venue / field | `Venue` (matched by title within the season, created with the venue's coordinates and timezone when absent) and `Ground` "Field *n*" (created when absent) |
| TBA participant | `UndecidedTeam` labelled "TBA" on the stage |

A division is created with a points formula derived from the competition's
MySideline ladder template (for example the NSW State Cup's "Events Ladder"
gives `4*win + 2*draw + 4*forfeit_for`), or the TFA standard ladder
(`3*win + 2*draw + 1*loss + 3*bye + 3*forfeit_for`) when the template cannot
be read; the forfeit score defaults from the template too. Ladder
configuration is not overwritten by later syncs and may be changed freely. A division or team created by hand with the same title as a
remote one is *adopted* (linked) on the first synchronisation rather than
duplicated, so ladder settings can be prepared before linking a season.

## Naming

MySideline is authoritative for everything *except* the names of divisions
and teams. Upstream naming is frequently unwieldy -- Central Coast Touch
publishes a division as "Born 2014 & 2013 u14 Boys" where "14 Boys" is what
should appear on the website -- so the `title` of a linked `Division` or
`Team` may be edited in the admin and the synchronisation will keep it.

Because the local name may be ours or theirs, and either side can change it
without telling the other, two copies of the remote name are kept beside our
own (both non-editable, set only by the synchronisation and the admin form):

| Field | Meaning |
| --- | --- |
| `title` | the name we publish |
| `mysideline_title` | what MySideline calls the record right now, refreshed on every synchronisation whether or not we use it |
| `mysideline_title_synced` | what MySideline called it when `title` was last reconciled with it: when the record was linked, when a remote rename was last applied, or when an administrator last saved it |

From these, `Division.mysideline_title_overridden` /
`Team.mysideline_title_overridden` (`title != mysideline_title_synced`) is
*our* variation and `mysideline_title_changed`
(`mysideline_title != mysideline_title_synced`) is *theirs*. The
synchronisation then:

* applies the remote name while the record has no local variation -- the
  behaviour before this feature and still the default, so nothing needs
  configuring for divisions whose upstream names are fine;
* keeps the local name when there is one, and **reports** an upstream rename
  of such a record (in `SyncResult.warnings`, the task log, the management
  command output and the *Synchronise with MySideline* admin page) so that
  somebody can decide which name is right. The record is never silently
  renamed and the upstream change is never silently discarded.

An administrator resolves a reported rename by editing the division or team:
the form shows what MySideline calls it and offers **Use the MySideline
name**, which discards the local name (and reverts the slug) so that later
renames are applied automatically again. Saving the form without ticking it
keeps the local name and acknowledges the remote change, so it is not
reported again until MySideline renames the record once more. Records
awaiting that decision are listed on the *Synchronise with MySideline* page
for the season.

`mysideline_renamed(queryset)` filters divisions or teams to those awaiting
a decision. The fields are added by migration `0064_mysideline_titles`,
which backfills existing links from their current titles so that nothing
already synchronised is reported as a variation.

Pools have no remote identifier -- they are matched by name -- so a pool
cannot be renamed locally; a local rename is treated as a new pool.

## Synchronisation semantics

The whole snapshot (association listing plus every selected competition) is
fetched before anything is written, then applied inside one transaction:

* **added** remotely: created locally (division, stage, pool, team, match,
  venue, ground as needed);
* **modified** remotely (date/time, field, teams, pool membership, bye):
  the corresponding fields are updated in place;
* **renamed** remotely: the local title and slug are updated unless the name
  has been changed locally (see [Naming](#naming)); identity is the
  MySideline id so relations (matches, registrations, ladders) are kept.
  Slugs marked as locked are left alone. A rename which would collide with
  another division in the season, or another team in the division, is
  reported and retried on the next synchronisation rather than failing;
* **scored** remotely: the scores are applied and the ladder is recalculated
  through the normal `Match` save signals. A result that is later changed or
  withdrawn is changed or cleared. A forfeit sets `is_forfeit`,
  `forfeit_winner` and the division's forfeit scores;
* **removed** remotely: matches are deleted; teams are deleted once their
  MySideline fixtures are gone, or detached (identifier cleared) when
  native matches or registrations reference them; pools and the finals
  stage are deleted once empty; a division is deleted when everything in it
  could be, otherwise it is kept, marked as *draft* and reported.

Only records carrying a MySideline identifier are ever changed or removed;
native divisions, teams and matches in the same season are untouched, and
venues and grounds are never removed.

A transport failure, HTTP error, GraphQL error or a response that does not
have the expected shape raises before the transaction starts, so a
temporary outage never empties a competition. A database error during the
apply rolls back the whole snapshot.

## Test data

`tournamentcontrol/competition/tests/fixtures/mysideline/state_cup_2025/`
holds the complete NSW State Cup 2025 (association 299999: 21 competitions,
242 teams, 959 matches, pools and finals) as captured from the interfaces
above, plus smaller captures of a club association. The unit tests and the
end-to-end test `tests/e2e/test_mysideline.py` import it through the real
client and reconciler with the HTTP layer replaced by
`tournamentcontrol.competition.tests.mysideline.state_cup_session`. Running
the end-to-end tests with `MYSIDELINE_LIVE=1` imports from the live site
instead, which confirms the remote interface still matches this document.

`state_cup_session(renames={...})` serves the same capture with names
substituted, which plays back an upstream rename without a second capture.
The end-to-end test uses it to walk the whole naming workflow through the
admin in a browser -- publishing local names for a division and a team,
having MySideline rename both underneath them, reviewing what the season's
*Synchronise with MySideline* page lists, then handing one name back and
keeping the other -- and screenshots each page as evidence
(`mysideline_admin_*.png`).
