import requests

from urlparse import parse_qsl, urlparse

from django.db.models import Max
from django.utils.text import slugify

from bs4 import BeautifulSoup
from dateutil.parser import parse

from tournamentcontrol.competition.models import Club, Match


def _next(manager, attr='order'):
    return (manager.aggregate(next=Max(attr))['next'] or 0) + 1


def sync(division):
    assert division.sportingpulse_url

    # Try to fetch the data from the specified SportingPulse URL
    source = requests.get(division.sportingpulse_url)
    assert source.status_code == 200

    ground_index = {}
    for venue in division.season.venues.select_related('grounds'):
        for ground in venue.grounds.all():
            ground_index[ground.title] = ground.pk

    stage_pool_index = {}
    for stage in division.stages.select_related('pools'):
        if stage.pools.count():
            for pool in stage.pools.all():
                stage_pool_index[pool.title] = (stage.pk, pool.pk)
        else:
            stage_pool_index[stage.title] = (stage.pk, None)

    # Use BeautifulSoup to construct a parse tree for data scraping
    soup = BeautifulSoup(source.content)

    # Initial values for content markers
    group = None
    round = None

    for row in soup.findAll('tr'):
        label = None

        # Fetch all the table data cells
        cols = row.findAll('td')

        # There are 2 linked fields, Venue and Match detail (in that order)
        links = row.findAll('a')

        # Marks the start of a Stage or StageGroup
        if len(cols) == 1:
            g = cols[0].text.strip()
            stage, group = stage_pool_index[g]

        elif cols:
            # Last link on the row holds the metadata for the match in the
            # external system.
            meta = dict(parse_qsl(urlparse(links[-1].attrs['href']).query))
            external_identifier = meta['fixture']

            # Round number & label
            r = cols[0].text.strip()
            l = cols[1].findAll('i')
            if r:
                round = r
            if l:
                label = l[0].text.strip()[1:-1]

            # Date, time, and place
            dt = parse("%s %s" % (cols[1].text.strip()[:8],
                                  cols[2].text.strip()), dayfirst=True)
            play_at = ground_index.get(cols[3].text.strip())

            # Teams & scores
            home_team_score = cols[4].text.strip()
            home_team = cols[5].text.strip()
            away_team = cols[7].text.strip()
            away_team_score = cols[8].text.strip()

            try:
                home_club = division.season.competition.clubs.get(
                    title=home_team)
            except Club.DoesNotExist:
                home_club = None

            try:
                away_club = division.season.competition.clubs.get(
                    title=away_team)
            except Club.DoesNotExist:
                away_club = None

            home_team, __ = division.teams.get_or_create(
                title=home_team, defaults={'slug': slugify(home_team),
                                           'club': home_club,
                                           'order': _next(division.teams)})

            away_team, __ = division.teams.get_or_create(
                title=away_team, defaults={'slug': slugify(away_team),
                                           'club': away_club,
                                           'order': _next(division.teams)})

            defaults = {
                'stage_id': stage,
                'stage_group_id': group,
                'round': round,
                'label': label,
                'date': dt.date(),
                'time': dt.time(),
                'play_at_id': play_at,
                'home_team': home_team,
                'home_team_score': home_team_score or None,
                'away_team': away_team,
                'away_team_score': away_team_score or None,
            }

            # Create or Update the match record based on scraped data.
            match, created = Match.objects.get_or_create(
                external_identifier=external_identifier, defaults=defaults)

            if not created:
                for k, v in defaults.items():
                    setattr(match, k, v)

            match.clean()
            match.save()
