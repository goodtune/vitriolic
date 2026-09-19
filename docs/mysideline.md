# MySideline synchronisation

Vitriolic can mirror the competitions that Touch Football Australia publishes
on [MySideline](https://tfa.mysideline.com.au) into a `Season`. MySideline is
authoritative for everything it manages: each synchronisation fetches a
complete snapshot of the remote competitions and converges the local
divisions, pools, teams, fixtures and results onto it.

This replaces the SportingPulse scraper that was removed in 2017 (the
`Division.sportingpulse_url` field it left behind is dropped by migration
`0063_mysideline`).

## Configuration

On the season edit form set **MySideline URL** to the association page, for
example `https://tfa.mysideline.com.au/competitions/association/6338`. The
URL is validated and normalised; only the association id is used internally.

An association page lists every competition it has ever published, across
years. Two optional filters narrow the selection:

* **MySideline season** -- the year MySideline files the competition under
  (`season` in the remote data), eg. `2026`.
* **MySideline season period** -- MySideline's `seasonTag`: `1` for the
  first half of the year (winter competitions), `2` for the second half
  (summer/spring competitions).

Leave both blank to mirror every competition listed for the association.

## Invocation

* **Admin**: seasons with a MySideline URL show a *MySideline* button in the
  season list which queues a synchronisation.
* **Celery**: `tournamentcontrol.competition.tasks.synchronise_mysideline`
  synchronises every enabled, incomplete season with a URL, isolating
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

* Match `status` values seen: `pre-game`, `final`, `forfeit`. Scores for a
  `pre-game` match are `0/0` and are ignored; only `final` supplies a
  result. `forfeit` carries `meta.forfeitingTeam`. Any other status is
  treated as unplayed so an unknown value never fabricates a result.
* A bye is a match with `meta.isBye` and one side empty. Finals whose
  participants are not yet known have `meta.isTba` and both sides empty.
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
| association | `Season` (`mysideline_url`) |
| competition | `Division` (`mysideline_id`); title and slug follow the remote name |
| `Regular` rounds | `Stage` "Regular Season" |
| `Final` rounds | `Stage` "Finals" (created only when finals fixtures exist; `Match.label` carries the round's display name, eg. "Grand Final") |
| pool | `StageGroup` on the regular stage; `Team.stage_group` and, for intra-pool matches, `Match.stage_group` |
| team | `Team` (`mysideline_id`); title and slug follow the remote name |
| match | `Match` (`mysideline_id`): round number, date/time in the venue's timezone, `play_at`, teams, scores, bye, forfeit |
| venue / field | `Venue` (matched by title within the season, created with the venue's coordinates and timezone when absent) and `Ground` "Field *n*" (created when absent) |
| TBA participant | `UndecidedTeam` labelled "TBA" on the stage |

A division is created with the TFA standard ladder as its points formula
(`3*win + 2*draw + 1*loss + 3*bye + 3*forfeit_for`, forfeit scores 5/0).
Ladder configuration is not managed by MySideline and may be changed freely
afterwards. A division or team created by hand with the same title as a
remote one is *adopted* (linked) on the first synchronisation rather than
duplicated, so ladder settings can be prepared before linking a season.

## Synchronisation semantics

The whole snapshot (association listing plus every selected competition) is
fetched before anything is written, then applied inside one transaction:

* **added** remotely: created locally (division, stage, pool, team, match,
  venue, ground as needed);
* **modified** remotely (date/time, field, teams, pool membership, bye):
  the corresponding fields are updated in place;
* **renamed** remotely: the local title and slug are updated; identity is the
  MySideline id so relations (matches, registrations, ladders) are kept.
  Slugs marked as locked are left alone;
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
