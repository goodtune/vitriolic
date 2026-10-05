# MySideline

MySideline (`https://tfa.mysideline.com.au`) is the competition management
platform used by Touch Football Australia and other NRL community sports. It
is one of the [upstream providers](upstream.md) a `Season` can be
synchronised from; this document describes the remote interface and what is
specific to MySideline. The configuration, identifiers, naming rules and
synchronisation semantics shared by every provider are in
[upstream.md](upstream.md).

## Configuration

A MySideline *association* corresponds to a Vitriolic `Competition`, and each
"year" the association page lets you pick corresponds to a `Season`:

1. On the competition set **Upstream URL** to the association page, for
   example `https://tfa.mysideline.com.au/competitions/association/299999`
   (NSW State Cup). Query parameters copied from the site's filter link are
   accepted and dropped.
2. On each season set **Upstream URL** to the association page filtered to
   the year, as the site's *Year* drop-down produces it:
   `https://tfa.mysideline.com.au/competitions/association/299999?season=2025`.
   Add the period drop-down's `seasonTag` -- `1` for the first half of the
   year (winter competitions), `2` for the second half (summer/spring) --
   when one Vitriolic season should cover only part of a year:
   `...?season=2025&seasonTag=2`.

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
      competition (69295321)       -> Division.upstream_id "mysideline:69295321"
        team (69333380)            -> Team.upstream_id "mysideline:69333380"
        pool ("Pool A", by name)   -> StageGroup (title)
        match (1388870728)         -> Match.upstream_id "mysideline:1388870728"
          round { number, type: Regular|Final, displayName }
          status: pre-game | final | forfeit
          venue { _id, name, venueTimezone }, meta.fieldNo

Pools have no identifier, only a name; they are matched by title.

### Observed behaviour and limitations

* The association page lists every competition the association has ever
  published; its *Year* / *Age* / period drop-downs are client-side filters
  mirrored into `?season=`, `?age=` and `?seasonTag=` query parameters, not
  separate requests. The season URL's `season` and `seasonTag` select the
  competitions the same way.
* Match `status` values seen: `pre-game`, `final` (occasionally `Final` on
  byes; statuses are lower-cased), `forfeit`. MySideline does not reliably
  promote a played match to `final`: most keep `pre-game` while their score
  is published, so a match that has started and carries a non-zero score is
  taken as played whatever its status; an unplayed match always reports
  `0/0`, `in-progress` is never a result, and a genuine 0-0 draw left at
  `pre-game` cannot be told from an unplayed fixture. `forfeit` carries
  `meta.forfeitingTeam`. Any other status is treated as unplayed so an
  unknown value never fabricates a result.
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
| association | `Competition` (`upstream_url`) |
| year / period | `Season` (`upstream_url` with `season` and optional `seasonTag`) |
| competition | `Division` (`upstream_id`) |
| `Regular` / `Final` rounds | `Stage` "Regular Season" / "Finals" |
| pool | `StageGroup` on the regular stage |
| team | `Team` (`upstream_id`) |
| match | `Match` (`upstream_id`): round, date/time in the venue's time zone, teams, scores, bye, forfeit |
| venue / field | `Venue` (with coordinates and `venueTimezone`) and `Ground` "Field *n*" |
| TBA participant | `UndecidedTeam` "TBA" |
| `laddertemplate` | the division's points formula and forfeit score when the division is created (for example the NSW State Cup's "Events Ladder" gives `4*win + 2*draw + 4*forfeit_for`) |

## Test data

`tournamentcontrol/competition/tests/fixtures/mysideline/state_cup_2025/`
holds the complete NSW State Cup 2025 (association 299999: 21 competitions,
242 teams, 959 matches, pools and finals) as captured from the interfaces
above, plus smaller captures of a club association. The unit tests
(`tests/test_mysideline.py`) and the end-to-end test
`tests/e2e/test_mysideline.py` import it through the real client and
reconciler with the HTTP layer replaced by
`tournamentcontrol.competition.tests.upstream.state_cup_session`. Running
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
