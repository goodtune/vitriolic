# revolutioniseSPORT

revolutioniseSPORT (`https://www.revolutionise.com.au`) is a hosted club and
association management platform used by hockey, water polo, squash and many
other sports. Each organisation has a public site under
`https://www.revolutionise.com.au/<slug>/` whose *Draws & results* module
publishes competitions, grades, rounds, fixtures, results and ladders. It is
one of the [upstream providers](upstream.md) a `Season` can be synchronised
from; this document describes the remote interface and what is specific to
revolutioniseSPORT. The configuration, identifiers, naming rules and
synchronisation semantics shared by every provider are in
[upstream.md](upstream.md).

## Configuration

A revolutioniseSPORT organisation corresponds to a Vitriolic `Competition`;
one of its competitions (or all of them) corresponds to a `Season`:

1. On the competition set **Upstream URL** to the organisation's draws
   index, for example `https://www.revolutionise.com.au/ccha/games` (Central
   Coast Hockey Association). Any page of the organisation is accepted and
   reduced to this.
2. On each season set **Upstream URL** to the competition's draws page, for
   example `https://www.revolutionise.com.au/ccha/games/25527` ("CCHA Mens
   Competition"); a grade or round page under it is accepted and reduced to
   the competition. Set it to the index (`.../ccha/games`) instead to mirror
   every competition the organisation currently publishes into one season.

A competition's grades become the season's divisions. Several
revolutioniseSPORT competitions that run concurrently (CCHA publishes
separate Mens, Womens and Junior competitions each winter) are either
separate Vitriolic competitions with a season each, or one season linked to
the index. The index only lists what the organisation currently publishes,
so prefer a competition URL for a season that should keep its data once the
organisation retires the competition from its site, and mark seasons
*complete* when they are over.

## Remote interface

There is no public API. The site is rendered server-side (a Laravel
application producing plain Bootstrap HTML with no data layer embedded in
the page), asking for JSON by `Accept` header or a `.json` suffix is refused
(403), and a separate *live scoring* site requires a login. The only
machine-readable export is a per-team iCalendar feed, which carries no
results. The public pages are therefore scraped with BeautifulSoup. No
cookies, tokens or browser headers are required and no rate limiting has
been observed; the pages are served by the application itself (New Relic
instrumentation, no CDN cache).

| Page | Purpose |
| --- | --- |
| `/<slug>/games` | the index: every competition currently published, as a heading with a *Download* link (`/reports/games/<competition>`) followed by its grades (`/games/<competition>/<grade>`) |
| `/<slug>/games/<competition>/<grade>` | the grade: a heading "*competition* · *grade*", a *View ladder* button when the grade keeps a ladder, and one row per round linking to `/round/<n>` with the round's name and dates |
| `/<slug>/games/<competition>/<grade>/round/<n>` | the round: a heading with the round's dates, one card per fixture, then a *BYEs* section naming the teams without a game |
| `/<slug>/pointscore/<competition>/<grade>` | the ladder: a table with Team, Played, Wins, Draws, Losses, Forfeits, For, Against, Diff. and Points |
| `/<slug>/games/team/export/ical/<competition>/<team>` | a team's fixtures as iCalendar; `DTSTART;TZID=Australia/Sydney:...` is the only place the site states a time zone |
| `/<slug>/game/<id>` | a fixture's page: the result or forfeit, date and time, venue with its street address, field, umpires and an embedded Google map whose URL carries the venue's coordinates (`!2d<lng>!3d<lat>`) when the organisation placed the venue on the map, or only its address otherwise |

Other pages exist but are not used: `/<slug>/games/<competition>` and
`/<slug>/games/<competition>/0/round/<n>` list every grade's fixtures for a
round without saying which grade each belongs to; `/<slug>/venues/<competition>/<venue>`
lists a venue's fixtures by date; `/<slug>/reports/games/...` and
`/<slug>/reports/pointscore/...` are PDFs of the same data.

### A fixture card

Each `div.card.card-hover` on a round page holds, in order: the date
("Fri 20 Mar 2026") and time ("20:00"), a link to the venue
(`/venues/<competition>/<venue>`) with the field name in the following `div`
(empty when the venue has no fields), the home team link
(`/games/team/<competition>/<team>`), the score as `<b>6 - 1</b>` or the word
`vs` when there is none, the away team link, an optional badge beside a team
-- `FF` "forced forfeit" or `FL` "forced loss", with a note such as "Team
Forfeit (Notified)" -- the umpires, and a *Details* link to `/game/<id>`,
which is the fixture's identifier. A forfeit may be shown with the score the
organisation entered (`5 - 0`) or with no score at all.

### Identifiers and hierarchy

revolutioniseSPORT uses integer identifiers:

    organisation ("ccha")
      competition (25527 "CCHA Mens Competition")
        grade (3741 "Mens Division 1")   -> Division.upstream_id "revolutionise:25527/3741"
          round (1..23, named)           -> Match.round, Stage by name
          team (405386)                  -> Team.upstream_id "revolutionise:405386"
          game (2433163)                 -> Match.upstream_id "revolutionise:2433163"
          bye (no identifier)            -> Match.upstream_id "revolutionise:bye/3741/5/405387"
        venue (3007), field (by name)    -> Venue, Ground

A grade is a persistent entity of the organisation that is attached to each
year's competition (Mens Division 1 is 3741 every year), so a division is
identified by competition *and* grade. Team ids are issued per competition
entry (Erina has a different id in each grade and each year), and game ids
are global. A bye has no page or id of its own; it is identified by grade,
round and team.

### Observed behaviour and limitations

* Rounds are numbered consecutively through the finals; only the name
  changes ("Round 20", "Semi Finals", "Finals", "Grand Finals"). A round
  whose name contains *final*, *semi*, *quarter*, *prelim*, *elimination*,
  *play-off* or *knockout* is treated as a finals round; anything else is a
  regular round. Finals fixtures carry the round name as the match label.
* Dates and times are shown in the organisation's local time with no zone,
  in whichever clock the organisation configured (`20:00` at CCHA, `8:00AM`
  at Water Polo Australia). The time zone is read once per competition from
  a team's iCalendar feed; if that cannot be read the season's time zone is
  used.
* A fixture is taken as played when a score is shown. The site shows
  `vs` for an unplayed fixture, so a published 0-0 is a result (unlike
  MySideline). Byes count once the round's last date has passed.
* Both `FF` and `FL` badges are treated as a forfeit by the badged team; the
  division's forfeit scores apply, whatever score was shown.
* Pools are not a feature of the draws module; organisations that pool a
  competition publish each pool as a separate grade (Squash Australia's
  "Australian Team Championships Pool A" and "Pool B"), so a division never
  has pools and cross-pool finals appear as a further grade.
* A finals fixture whose participants are not yet known shows "To be
  determined" in place of a team (QUT Netball's finals); it is represented
  locally with a "TBA" undecided team until the teams are filled in, as for
  MySideline.
* Round notes ("Friday night open - Erina") and umpire appointments are not
  imported.
* The points scheme is not published. It is inferred from the ladder totals
  (see below); until a few results are in, the division is created with the
  default formula and the synchronisation says so.
* The index only lists competitions the organisation is currently showing;
  a competition without draws yet ("Summer Comp 2026") appears on the
  ladders index but not the draws index, and a season linked to it fails to
  synchronise (nothing is written) until its draws are published.
* The HTML structure (Bootstrap class names) is the fragile part of the
  integration; the parsers look for links by URL shape rather than by class
  wherever they can.

## Mapping onto Vitriolic

| revolutioniseSPORT | Vitriolic |
| --- | --- |
| organisation | `Competition` (`upstream_url`) |
| competition (or the index) | `Season` (`upstream_url`) |
| grade | `Division` (`upstream_id`); when one season mirrors several competitions with a grade of the same name, the competition's name is appended in brackets |
| rounds named "Round *n*" / finals rounds | `Stage` "Regular Season" / "Finals" |
| team | `Team` (`upstream_id`); the ladder's order gives the initial team order |
| game | `Match` (`upstream_id`): round, date and time in the competition's time zone, venue and field, teams, scores, forfeit |
| bye | `Match` with `is_bye`, dated by the round, `bye_processed` once the round has passed |
| venue / field | `Venue` (with coordinates and address from a game page, time zone from the iCalendar feed) and `Ground` (the field's name as published, eg. "Elaine Johnston Pitch") |
| ladder totals | the division's points formula and forfeit score when the division is created |

### Inferring the points scheme

The ladder gives each team's wins, draws, losses, forfeits and points, and
for some sports a *Bonus* column (Water Polo Australia awards and deducts
bonus points) which is added to the total as it stands. The points per
outcome are found as the unique small-integer solution (0-6 for a
win, 0-4 a draw, 0-3 a loss, -3 to 3 a loss by forfeit, 0-6 a bye) of
`wins*W + draws*D + losses*L + forfeits*F = points` over every row; outcomes
that no team has yet (no draws, no forfeits) are not constrained and take
defaults (one point for a draw, nothing for a loss by forfeit or a bye), and
the synchronisation notes the assumption. A win by forfeit is counted as a
win on the ladder, so `forfeit_for` is given the win points. If the totals
admit more than one scheme, or nothing has been played, the TFA standard
ladder is applied and reported. CCHA's 2026 competitions resolve to
`3*win + 2*draw + 1*loss + 3*forfeit_for`, with byes counting for nothing
and not as played; QUT Netball's to the same with a point deducted for a
forfeit (`+ -1*forfeit_against`); Water Polo Australia's championships to
3 for a win and nothing for a loss, with bonus points added. The forfeit score is the score most often shown for a
forfeit in the grade (5 for CCHA), or the default when none was shown.

### Request volume

A synchronisation of one competition makes one request for the index, then
per grade one for the grade page, one per round and one for the ladder,
plus one iCalendar feed per competition and one game page per venue: 78
requests for CCHA's three-grade Mens competition. Pages are not cached
between synchronisations.

## Test data

`tournamentcontrol/competition/tests/fixtures/revolutionise/` holds the
Central Coast Hockey Association's 2026 Mens competition (25527: three
grades, 23 rounds each including finals, 170 fixtures with byes and a
forfeit) as captured from the pages above on 5 October 2026, reduced to the
page content the scraper reads, plus the draws and ladders indexes and
single pages showing a forfeit without a score, a grade without a ladder, a
competition without draws and fixtures yet to be played, and pages from
Water Polo Australia (12-hour times, a ladder with bonus points, a venue
without map coordinates) and QUT Netball (finalists to be determined).
`capture.txt` maps each file to the URL it was served from. The unit tests
(`tests/test_revolutionise.py`) import it through the real client and
reconciler with the HTTP layer replaced by
`tournamentcontrol.competition.tests.upstream.ccha_session`, which also
accepts `renames={...}` to play back an upstream rename.
