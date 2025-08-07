"""Factory classes for creating test data in E2E tests."""
import factory
from django.contrib.auth.models import User
from factory.django import DjangoModelFactory

# Import the actual models - these paths may need adjustment based on the project structure
try:
    from touchtechnology.common.models import SitemapNode
    from touchtechnology.news.models import Article
    from tournamentcontrol.competition.models import (
        Competition, Season, Division, Team, Club, Place, Match
    )
    MODELS_AVAILABLE = True
except ImportError:
    MODELS_AVAILABLE = False


class UserFactory(DjangoModelFactory):
    """Factory for creating User instances."""
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@example.com")
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    is_active = True


class AdminUserFactory(UserFactory):
    """Factory for creating admin users."""
    is_staff = True
    is_superuser = True
    username = "admin"
    email = "admin@example.com"


if MODELS_AVAILABLE:
    class CompetitionFactory(DjangoModelFactory):
        """Factory for creating Competition instances."""
        class Meta:
            model = Competition

        title = factory.Faker("company")
        abbreviation = factory.Faker("lexify", text="???", letters="ABCDEFGHIJKLMNOPQRSTUVWXYZ")


    class SeasonFactory(DjangoModelFactory):
        """Factory for creating Season instances."""
        class Meta:
            model = Season

        competition = factory.SubFactory(CompetitionFactory)
        title = factory.LazyAttribute(lambda obj: f"{obj.year} Season")
        year = factory.Faker("year")


    class DivisionFactory(DjangoModelFactory):
        """Factory for creating Division instances."""
        class Meta:
            model = Division

        season = factory.SubFactory(SeasonFactory)
        title = factory.Sequence(lambda n: f"Division {n}")
        abbreviation = factory.Sequence(lambda n: f"D{n}")
        order = factory.Sequence(lambda n: n)


    class ClubFactory(DjangoModelFactory):
        """Factory for creating Club instances."""
        class Meta:
            model = Club

        title = factory.Faker("company")
        abbreviation = factory.Faker("lexify", text="???", letters="ABCDEFGHIJKLMNOPQRSTUVWXYZ")


    class TeamFactory(DjangoModelFactory):
        """Factory for creating Team instances."""
        class Meta:
            model = Team

        club = factory.SubFactory(ClubFactory)
        title = factory.Faker("company")
        abbreviation = factory.Faker("lexify", text="???", letters="ABCDEFGHIJKLMNOPQRSTUVWXYZ")


    class PlaceFactory(DjangoModelFactory):
        """Factory for creating Place instances (fields/venues)."""
        class Meta:
            model = Place

        title = factory.Sequence(lambda n: f"Field {n}")
        abbreviation = factory.Sequence(lambda n: f"F{n}")


    class LargeCompetitionDataFactory:
        """Factory for creating large datasets for performance testing."""
        
        @classmethod
        def create_large_season(cls, num_divisions=5, teams_per_division=8, num_fields=6):
            """
            Create a season with large amounts of data for performance testing.
            
            Args:
                num_divisions: Number of divisions to create
                teams_per_division: Number of teams per division  
                num_fields: Number of playing fields
                
            Returns:
                Season instance with associated data
            """
            # Create competition and season
            season = SeasonFactory()
            
            # Create fields
            fields = [PlaceFactory() for _ in range(num_fields)]
            
            # Create divisions with teams
            divisions = []
            all_teams = []
            
            for i in range(num_divisions):
                division = DivisionFactory(season=season, order=i+1)
                divisions.append(division)
                
                # Create teams for this division
                division_teams = []
                for j in range(teams_per_division):
                    team = TeamFactory()
                    division_teams.append(team)
                    all_teams.append(team)
                
                # Create matches for round-robin style tournament
                matches = []
                for home_idx, home_team in enumerate(division_teams):
                    for away_idx, away_team in enumerate(division_teams):
                        if home_idx != away_idx:  # No team plays itself
                            match = Match.objects.create(
                                stage=division.stages.first(),  # Assuming divisions have stages
                                home_team=home_team,
                                away_team=away_team,
                                round=1,  # Simplified - all matches in round 1
                            )
                            matches.append(match)
            
            return {
                'season': season,
                'divisions': divisions,
                'teams': all_teams,
                'fields': fields,
                'total_matches': len(Match.objects.filter(stage__division__season=season))
            }


def create_minimal_site_structure():
    """Create minimal site structure for testing."""
    if not MODELS_AVAILABLE:
        return None
        
    # This would create the basic sitemap structure
    # Implementation depends on the actual SitemapNode model structure
    pass