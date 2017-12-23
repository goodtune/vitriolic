# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import django.db.models.deletion
import touchtechnology.common.db.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Club',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('title', models.CharField(max_length=255, verbose_name='Title')),
                ('short_title', models.CharField(help_text='This is used in navigation menus instead of the longer title value.', max_length=100, verbose_name='Short title', blank=True)),
                ('slug', models.SlugField(max_length=255, verbose_name='Slug')),
                ('slug_locked', models.BooleanField(default=False, verbose_name='Slug locked')),
                ('email', models.EmailField(max_length=255, blank=True)),
                ('website', models.URLField(max_length=255, blank=True)),
                ('twitter', models.CharField(help_text=b'Official Twitter name for use in social "mentions"', max_length=50, blank=True)),
                ('abbreviation', models.CharField(help_text=b'Optional 3-letter abbreviation to be used on scoreboards.', max_length=3, blank=True)),
            ],
            options={
                'ordering': ('title',),
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='ClubAssociation',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('club', touchtechnology.common.db.models.ForeignKey(related_name=b'staff', to='competition.Club')),
            ],
            options={
                'ordering': ('person__last_name', 'person__first_name'),
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='ClubRole',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=50)),
            ],
            options={
                'ordering': ('name',),
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Competition',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('title', models.CharField(max_length=255, verbose_name='Title')),
                ('short_title', models.CharField(help_text='This is used in navigation menus instead of the longer title value.', max_length=100, verbose_name='Short title', blank=True)),
                ('slug', models.SlugField(max_length=255, verbose_name='Slug')),
                ('slug_locked', models.BooleanField(default=False, verbose_name='Slug locked')),
                ('order', models.PositiveIntegerField(default=1)),
                ('copy', touchtechnology.common.db.models.HTMLField(blank=True)),
                ('enabled', models.BooleanField(default=True)),
                ('clubs', touchtechnology.common.db.models.ManyToManyField(related_name=b'competitions', null=True, to='competition.Club', blank=True)),
            ],
            options={
                'ordering': ('order',),
                'abstract': False,
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Division',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('title', models.CharField(max_length=255, verbose_name='Title')),
                ('short_title', models.CharField(help_text='This is used in navigation menus instead of the longer title value.', max_length=100, verbose_name='Short title', blank=True)),
                ('slug', models.SlugField(max_length=255, verbose_name='Slug')),
                ('slug_locked', models.BooleanField(default=False, verbose_name='Slug locked')),
                ('order', models.PositiveIntegerField(default=1)),
                ('points_formula', models.TextField(null=True, verbose_name='Points system', blank=True)),
                ('bonus_points_formula', models.TextField(null=True, blank=True)),
                ('forfeit_for_score', models.SmallIntegerField(null=True)),
                ('forfeit_against_score', models.SmallIntegerField(null=True)),
                ('include_forfeits_in_played', models.BooleanField(default=False)),
                ('games_per_day', models.SmallIntegerField(help_text=b'\n        In Tournament mode, specify how many matches per day should be scheduled\n        by the automatic draw generator.', null=True)),
            ],
            options={
                'ordering': ('order',),
                'abstract': False,
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='DivisionExclusionDate',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date', touchtechnology.common.db.models.DateField()),
                ('division', touchtechnology.common.db.models.ForeignKey(related_name=b'exclusions', to='competition.Division')),
            ],
            options={
                'verbose_name': 'Exclusion Date',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='DrawFormat',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=50)),
                ('text', models.TextField(verbose_name='Formula')),
                ('teams', models.PositiveIntegerField(null=True, blank=True)),
                ('is_final', models.BooleanField(default=False)),
            ],
            options={
                'ordering': ('is_final', 'teams', 'name'),
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='LadderEntry',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('played', models.SmallIntegerField(default=0)),
                ('win', models.SmallIntegerField(default=0)),
                ('loss', models.SmallIntegerField(default=0)),
                ('draw', models.SmallIntegerField(default=0)),
                ('bye', models.SmallIntegerField(default=0)),
                ('forfeit_for', models.SmallIntegerField(default=0)),
                ('forfeit_against', models.SmallIntegerField(default=0)),
                ('score_for', models.SmallIntegerField(default=0)),
                ('score_against', models.SmallIntegerField(default=0)),
                ('bonus_points', models.SmallIntegerField(default=0)),
                ('points', models.DecimalField(default=0, max_digits=6, decimal_places=3)),
            ],
            options={
                'abstract': False,
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='LadderSummary',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('played', models.SmallIntegerField(default=0)),
                ('win', models.SmallIntegerField(default=0)),
                ('loss', models.SmallIntegerField(default=0)),
                ('draw', models.SmallIntegerField(default=0)),
                ('bye', models.SmallIntegerField(default=0)),
                ('forfeit_for', models.SmallIntegerField(default=0)),
                ('forfeit_against', models.SmallIntegerField(default=0)),
                ('score_for', models.SmallIntegerField(default=0)),
                ('score_against', models.SmallIntegerField(default=0)),
                ('bonus_points', models.SmallIntegerField(default=0)),
                ('points', models.DecimalField(default=0, max_digits=6, decimal_places=3)),
                ('difference', models.DecimalField(default=0, max_digits=6, decimal_places=3)),
                ('percentage', models.DecimalField(null=True, max_digits=10, decimal_places=2)),
            ],
            options={
                'ordering': ('stage', '-points', '-difference', '-percentage', 'team__title'),
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Match',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('label', models.CharField(max_length=100, null=True, blank=True)),
                ('home_team_eval', models.CharField(max_length=10, null=True, blank=True)),
                ('away_team_eval', models.CharField(max_length=10, null=True, blank=True)),
                ('evaluated', models.NullBooleanField()),
                ('is_washout', models.BooleanField(default=False)),
                ('date', touchtechnology.common.db.models.DateField(null=True, blank=True)),
                ('time', touchtechnology.common.db.models.TimeField(null=True, blank=True)),
                ('datetime', touchtechnology.common.db.models.DateTimeField(null=True, blank=True)),
                ('home_team_score', models.IntegerField(null=True, blank=True)),
                ('away_team_score', models.IntegerField(null=True, blank=True)),
                ('is_bye', models.BooleanField(default=False)),
                ('bye_processed', models.BooleanField(default=False)),
                ('is_forfeit', models.BooleanField(default=False)),
                ('round', models.IntegerField(null=True, blank=True)),
                ('include_in_ladder', models.BooleanField(default=True)),
            ],
            options={
                'ordering': ('date', 'stage', 'round', 'is_bye', 'time', 'play_at__ground__order', 'id'),
                'verbose_name_plural': 'matches',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Person',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('first_name', models.CharField(max_length=30)),
                ('last_name', models.CharField(max_length=30)),
                ('gender', models.CharField(max_length=1, choices=[(b'M', 'Male'), (b'F', 'Female')])),
                ('date_of_birth', touchtechnology.common.db.models.DateField(null=True, blank=True)),
                ('email', models.EmailField(max_length=75, blank=True)),
                ('home_phone', models.CharField(max_length=30, blank=True)),
                ('work_phone', models.CharField(max_length=30, blank=True)),
                ('mobile_phone', models.CharField(max_length=30, blank=True)),
                ('club', touchtechnology.common.db.models.ForeignKey(related_name=b'members', to='competition.Club')),
            ],
            options={
                'ordering': ('last_name', 'first_name'),
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Place',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('title', models.CharField(max_length=255, verbose_name='Title')),
                ('short_title', models.CharField(help_text='This is used in navigation menus instead of the longer title value.', max_length=100, verbose_name='Short title', blank=True)),
                ('slug', models.SlugField(max_length=255, verbose_name='Slug')),
                ('slug_locked', models.BooleanField(default=False, verbose_name='Slug locked')),
                ('order', models.PositiveIntegerField(default=1)),
                ('abbreviation', models.CharField(max_length=20, null=True, blank=True)),
                ('latlng', touchtechnology.common.db.models.LocationField(max_length=100)),
                ('timezone', models.CharField(blank=True, max_length=50, null=True)),
            ],
            options={
                'ordering': ('order',),
                'abstract': False,
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Ground',
            fields=[
                ('place_ptr', models.OneToOneField(parent_link=True, auto_created=True, primary_key=True, serialize=False, to='competition.Place')),
            ],
            options={
                'ordering': ('order',),
                'abstract': False,
            },
            bases=('competition.place',),
        ),
        migrations.CreateModel(
            name='Season',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('title', models.CharField(max_length=255, verbose_name='Title')),
                ('short_title', models.CharField(help_text='This is used in navigation menus instead of the longer title value.', max_length=100, verbose_name='Short title', blank=True)),
                ('slug', models.SlugField(max_length=255, verbose_name='Slug')),
                ('slug_locked', models.BooleanField(default=False, verbose_name='Slug locked')),
                ('order', models.PositiveIntegerField(default=1)),
                ('hashtag', models.CharField(help_text=b'Your official tag for social media promotions, excluding the # symbol.', max_length=30, null=True, verbose_name=b'Hash Tag', blank=True)),
                ('enabled', models.BooleanField(default=True)),
                ('start_date', touchtechnology.common.db.models.DateField(null=True, blank=True)),
                ('mode', models.IntegerField(default=2, help_text=b'Used by the draw wizard to help you set your match dates & times automatically.', choices=[(2, 'Season'), (3, 'Tournament')])),
                ('statistics', models.BooleanField(default=True, help_text=b'Set to No if you do not wish to keep scoring or most valuable player statistics.')),
                ('mvp_results_public', touchtechnology.common.db.models.DateTimeField(help_text=b'Set to prevent the front-end site revealing MVP points before the specified time.', null=True, blank=True)),
                ('complete', models.BooleanField(default=False, help_text=b'Set to indicate this season is in the past. Optimises progression calculations.')),
                ('timezone', models.CharField(blank=True, max_length=50, null=True)),
                ('competition', touchtechnology.common.db.models.ForeignKey(related_name=b'seasons', to='competition.Competition')),
            ],
            options={
                'ordering': ('order',),
                'abstract': False,
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='SeasonAssociation',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('club', models.ForeignKey(related_name=b'officials', to='competition.Club')),
                ('person', touchtechnology.common.db.models.ForeignKey(to='competition.Person')),
                ('roles', touchtechnology.common.db.models.ManyToManyField(to='competition.ClubRole')),
                ('season', models.ForeignKey(related_name=b'officials', to='competition.Season')),
            ],
            options={
                'ordering': ('club', 'season', 'person__last_name', 'person__first_name'),
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='SeasonExclusionDate',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date', touchtechnology.common.db.models.DateField()),
                ('season', touchtechnology.common.db.models.ForeignKey(related_name=b'exclusions', to='competition.Season')),
            ],
            options={
                'verbose_name': 'Exclusion Date',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='SeasonMatchTime',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('start', touchtechnology.common.db.models.TimeField()),
                ('interval', models.IntegerField()),
                ('count', models.IntegerField()),
                ('start_date', touchtechnology.common.db.models.DateField(null=True, verbose_name=b'From', blank=True)),
                ('end_date', touchtechnology.common.db.models.DateField(null=True, verbose_name=b'Until', blank=True)),
                ('season', touchtechnology.common.db.models.ForeignKey(related_name=b'timeslots', to='competition.Season')),
            ],
            options={
                'abstract': False,
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='SimpleScoreMatchStatistic',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('number', models.IntegerField(null=True, blank=True)),
                ('played', models.SmallIntegerField(default=0)),
                ('points', models.SmallIntegerField(default=0)),
                ('mvp', models.SmallIntegerField(default=0)),
                ('match', touchtechnology.common.db.models.ForeignKey(related_name=b'statistics', to='competition.Match')),
                ('player', touchtechnology.common.db.models.ForeignKey(related_name=b'statistics', to='competition.Person')),
            ],
            options={
                'ordering': ('match', 'number'),
                'abstract': False,
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Stage',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('title', models.CharField(max_length=255, verbose_name='Title')),
                ('short_title', models.CharField(help_text='This is used in navigation menus instead of the longer title value.', max_length=100, verbose_name='Short title', blank=True)),
                ('slug', models.SlugField(max_length=255, verbose_name='Slug')),
                ('slug_locked', models.BooleanField(default=False, verbose_name='Slug locked')),
                ('order', models.PositiveIntegerField(default=1)),
                ('keep_ladder', models.BooleanField(default=True, help_text=b'\n        Set this to <b>No</b> if this stage does not need to keep a competition ladder.<br />\n        Usually set to No for a Final Series or a Knockout stage.\n        ', verbose_name=b'Keep a ladder')),
                ('scale_group_points', models.BooleanField(default=False, help_text=b'\n        In stages with multiple pools, adjust points in the smaller groups to\n        compensate for the reduced opportunity to score points.<br />\n        You <strong>should</strong> also set 0 points for Bye matches.')),
                ('carry_ladder', models.BooleanField(default=False, help_text=b'\n        Set this to <b>Yes</b> if this stage should carry over values from the previous stage.\n        ', verbose_name=b'Carry over points')),
                ('keep_mvp', models.BooleanField(default=True, help_text=b'\n        Set this to <b>No</b> if this stage does not need to keep track of MVP points.<br />\n        Usually set to No for a Final Series.\n        ', verbose_name=b'Keep MVP stats')),
                ('division', touchtechnology.common.db.models.ForeignKey(related_name=b'stages', to='competition.Division')),
                ('follows', touchtechnology.common.db.models.ForeignKey(related_name=b'preceeds', on_delete=django.db.models.deletion.SET_NULL, blank=True, to='competition.Stage', help_text=b'\n        When progressing teams into this stage, which earlier stage should be used for\n        determining positions.<br />\n        Default is the immediately preceeding stage.\n        ', null=True)),
                ('matches_needing_printing', touchtechnology.common.db.models.ManyToManyField(related_name=b'to_be_printed', to='competition.Match', blank=True)),
            ],
            options={
                'ordering': ('order',),
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='StageGroup',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('title', models.CharField(max_length=255, verbose_name='Title')),
                ('short_title', models.CharField(help_text='This is used in navigation menus instead of the longer title value.', max_length=100, verbose_name='Short title', blank=True)),
                ('slug', models.SlugField(max_length=255, verbose_name='Slug')),
                ('slug_locked', models.BooleanField(default=False, verbose_name='Slug locked')),
                ('order', models.PositiveIntegerField(default=1)),
                ('carry_ladder', models.BooleanField(default=False, help_text=b'\n        Set this to <b>Yes</b> if the ladder for this pool should carry over values from\n        the previous stage.<br />\n        Will only apply for matches played against teams that are now in this group.\n        ', verbose_name=b'Carry over points')),
                ('stage', touchtechnology.common.db.models.ForeignKey(related_name=b'pools', to='competition.Stage')),
            ],
            options={
                'ordering': ('order',),
                'verbose_name': 'Pool',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Team',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('title', models.CharField(max_length=255, verbose_name='Title')),
                ('short_title', models.CharField(help_text='This is used in navigation menus instead of the longer title value.', max_length=100, verbose_name='Short title', blank=True)),
                ('slug', models.SlugField(max_length=255, verbose_name='Slug')),
                ('slug_locked', models.BooleanField(default=False, verbose_name='Slug locked')),
                ('order', models.PositiveIntegerField(default=1)),
                ('names_locked', models.BooleanField(default=False, help_text=b'\n        When the team name is locked, the team manager will not be able to change their team name.<br />\n        As a tournament manager you can always change the names.')),
                ('timeslots_after', touchtechnology.common.db.models.TimeField(help_text=b'Specify the earliest time that this team can play. Leave blank for no preference.', null=True, verbose_name=b'Start after', blank=True)),
                ('timeslots_before', touchtechnology.common.db.models.TimeField(help_text=b'Specify the latest time that this team can play. Leave blank for no preference.', null=True, verbose_name=b'Start before', blank=True)),
                ('club', touchtechnology.common.db.models.ForeignKey(related_name=b'teams', on_delete=django.db.models.deletion.SET_NULL, blank=True, to='competition.Club', null=True)),
                ('division', touchtechnology.common.db.models.ForeignKey(related_name=b'teams', blank=True, to='competition.Division', null=True)),
                ('stage_group', touchtechnology.common.db.models.ForeignKey(related_name=b'teams', on_delete=django.db.models.deletion.SET_NULL, verbose_name=b'Pool', blank=True, to='competition.StageGroup', null=True)),
                ('team_clashes', touchtechnology.common.db.models.ManyToManyField(help_text=b'Select any teams that must not play at the same time.', related_name='team_clashes_rel_+', verbose_name=b"Don't clash", to='competition.Team', blank=True)),
            ],
            options={
                'ordering': ('division__order', 'stage_group__order', 'order'),
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='TeamAssociation',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('number', models.IntegerField(null=True, blank=True)),
                ('is_player', models.BooleanField(default=True)),
                ('person', touchtechnology.common.db.models.ForeignKey(to='competition.Person', null=True)),
            ],
            options={
                'ordering': ('-is_player', 'number', 'person__last_name', 'person__first_name'),
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='TeamRole',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=50)),
                ('competition', touchtechnology.common.db.models.ForeignKey(related_name=b'team_roles', to='competition.Competition')),
            ],
            options={
                'ordering': ('name',),
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='UndecidedTeam',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('formula', models.CharField(max_length=20, blank=True)),
                ('label', models.CharField(max_length=30, blank=True)),
                ('stage', touchtechnology.common.db.models.ForeignKey(related_name=b'undecided_teams', to='competition.Stage')),
                ('stage_group', touchtechnology.common.db.models.ForeignKey(related_name=b'undecided_teams', on_delete=django.db.models.deletion.SET_NULL, verbose_name=b'Pool', blank=True, to='competition.StageGroup', null=True)),
            ],
            options={
                'ordering': ('stage_group', 'formula'),
                'verbose_name': 'team',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Venue',
            fields=[
                ('place_ptr', models.OneToOneField(parent_link=True, auto_created=True, primary_key=True, serialize=False, to='competition.Place')),
                ('season', touchtechnology.common.db.models.ForeignKey(related_name=b'venues', to='competition.Season')),
            ],
            options={
                'ordering': ('order',),
                'abstract': False,
            },
            bases=('competition.place',),
        ),
        migrations.AddField(
            model_name='teamassociation',
            name='roles',
            field=touchtechnology.common.db.models.ManyToManyField(to='competition.TeamRole', blank=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='teamassociation',
            name='team',
            field=touchtechnology.common.db.models.ForeignKey(related_name=b'people', to='competition.Team'),
            preserve_default=True,
        ),
        migrations.AlterUniqueTogether(
            name='teamassociation',
            unique_together=set([('team', 'person')]),
        ),
        migrations.AlterUniqueTogether(
            name='team',
            unique_together=set([('title', 'division')]),
        ),
        migrations.AlterUniqueTogether(
            name='stagegroup',
            unique_together=set([('stage', 'order')]),
        ),
        migrations.AlterUniqueTogether(
            name='stage',
            unique_together=set([('division', 'slug')]),
        ),
        migrations.AlterUniqueTogether(
            name='seasonexclusiondate',
            unique_together=set([('season', 'date')]),
        ),
        migrations.AlterUniqueTogether(
            name='seasonassociation',
            unique_together=set([('season', 'person')]),
        ),
        migrations.AddField(
            model_name='match',
            name='away_team',
            field=touchtechnology.common.db.models.ForeignKey(related_name=b'away_games', blank=True, to='competition.Team', null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='match',
            name='away_team_eval_related',
            field=touchtechnology.common.db.models.ForeignKey(related_name=b'+away_team_eval', blank=True, to='competition.Match', null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='match',
            name='away_team_undecided',
            field=touchtechnology.common.db.models.ForeignKey(related_name=b'away_games', blank=True, to='competition.UndecidedTeam', null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='match',
            name='forfeit_winner',
            field=touchtechnology.common.db.models.ForeignKey(related_name=b'+team', blank=True, to='competition.Team', null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='match',
            name='home_team',
            field=touchtechnology.common.db.models.ForeignKey(related_name=b'home_games', blank=True, to='competition.Team', null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='match',
            name='home_team_eval_related',
            field=touchtechnology.common.db.models.ForeignKey(related_name=b'+home_team_eval', blank=True, to='competition.Match', null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='match',
            name='home_team_undecided',
            field=touchtechnology.common.db.models.ForeignKey(related_name=b'home_games', blank=True, to='competition.UndecidedTeam', null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='match',
            name='play_at',
            field=touchtechnology.common.db.models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, to='competition.Place', null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='match',
            name='stage',
            field=touchtechnology.common.db.models.ForeignKey(related_name=b'matches', to='competition.Stage', null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='match',
            name='stage_group',
            field=touchtechnology.common.db.models.ForeignKey(related_name=b'matches', verbose_name=b'Pool', blank=True, to='competition.StageGroup', null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='laddersummary',
            name='stage',
            field=touchtechnology.common.db.models.ForeignKey(related_name=b'ladder_summary', to='competition.Stage'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='laddersummary',
            name='stage_group',
            field=touchtechnology.common.db.models.ForeignKey(related_name=b'ladder_summary', to='competition.StageGroup', null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='laddersummary',
            name='team',
            field=touchtechnology.common.db.models.ForeignKey(related_name=b'ladder_summary', to='competition.Team'),
            preserve_default=True,
        ),
        migrations.AlterUniqueTogether(
            name='laddersummary',
            unique_together=set([('stage', 'team')]),
        ),
        migrations.AddField(
            model_name='ladderentry',
            name='match',
            field=touchtechnology.common.db.models.ForeignKey(related_name=b'ladder_entries', to='competition.Match'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='ladderentry',
            name='opponent',
            field=touchtechnology.common.db.models.ForeignKey(to='competition.Team', null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='ladderentry',
            name='team',
            field=touchtechnology.common.db.models.ForeignKey(related_name=b'ladder_entries', to='competition.Team'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='ground',
            name='venue',
            field=touchtechnology.common.db.models.ForeignKey(related_name=b'grounds', to='competition.Venue'),
            preserve_default=True,
        ),
        migrations.AlterUniqueTogether(
            name='divisionexclusiondate',
            unique_together=set([('division', 'date')]),
        ),
        migrations.AddField(
            model_name='division',
            name='season',
            field=touchtechnology.common.db.models.ForeignKey(related_name=b'divisions', to='competition.Season'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='clubrole',
            name='competition',
            field=touchtechnology.common.db.models.ForeignKey(related_name=b'club_roles', to='competition.Competition'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='clubassociation',
            name='person',
            field=touchtechnology.common.db.models.ForeignKey(to='competition.Person'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='clubassociation',
            name='roles',
            field=touchtechnology.common.db.models.ManyToManyField(to='competition.ClubRole'),
            preserve_default=True,
        ),
        migrations.AlterUniqueTogether(
            name='clubassociation',
            unique_together=set([('club', 'person')]),
        ),
        migrations.AddField(
            model_name='club',
            name='primary',
            field=touchtechnology.common.db.models.ForeignKey(related_name=b'+club', blank=True, to='competition.Person', help_text=b'Appears on the front-end with other club information.', null=True, verbose_name=b'Primary contact'),
            preserve_default=True,
        ),
        migrations.CreateModel(
            name='ByeTeam',
            fields=[
            ],
            options={
                'proxy': True,
            },
            bases=('competition.team',),
        ),
    ]
