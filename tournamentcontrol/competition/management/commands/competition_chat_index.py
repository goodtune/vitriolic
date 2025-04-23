import faiss
import numpy as np
import json
import fasttext
import fasttext.util
from django.core.management.base import BaseCommand
from tournamentcontrol.competition.models import Competition, Season, Team, Person, SimpleScoreMatchStatistic


class Command(BaseCommand):
    help = "Generate FAISS index for chatbot queries using FastText embeddings"

    def handle(self, *args, **kwargs):
        self.stdout.write("Loading FastText model...")
        fasttext.util.download_model('en', if_exists='ignore')  # Download English model if not already present
        ft = fasttext.load_model('cc.en.300.bin')  # Load 300-dimensional word vectors

        def get_embedding(text):
            """Generate sentence embeddings by averaging word vectors."""
            words = text.split()
            vectors = [ft.get_word_vector(word) for word in words if word in ft.words]
            return np.mean(vectors, axis=0) if vectors else np.zeros(300)

        # Prepare data for embedding
        dataset = []
        metadata = []

        self.stdout.write("Extracting data from models...")

        # Extract data from models
        competitions = Competition.objects.all()
        for competition in competitions:
            dataset.append(f"Competition: {competition.title}")
            metadata.append({"type": "competition", "id": competition.pk})

        teams = Team.objects.all()
        for team in teams:
            players = "; ".join(str(ta) for ta in team.people.filter(is_player=True))
            dataset.append(f"Team: {team.title}. Players: {players}.")
            metadata.append({"type": "team", "id": team.pk})

        people = Person.objects.all()
        for person in people:

            dataset.append(f"Person: {person.get_full_name}. Games Played: {person.stats['played']}")
            metadata.append({"type": "person", "id": person.pk})

        matches = SimpleScoreMatchStatistic.objects.all()
        for match in matches:
            dataset.append(f"Match: {match.match.name}. Points scored: {match.points}.")
            metadata.append({"type": "match_statistics", "id": match.pk})

        print(dataset)
        print(metadata)

        # Generate embeddings
        self.stdout.write("Generating embeddings...")
        embeddings = np.array([get_embedding(text) for text in dataset], dtype=np.float32)

        # Build FAISS index
        self.stdout.write("Building FAISS index...")
        dimension = embeddings.shape[1]
        index = faiss.IndexFlatL2(dimension)
        index.add(embeddings)

        # Save index and metadata
        faiss.write_index(index, "faiss_index.bin")
        with open("metadata.json", "w") as f:
            json.dump(metadata, f)

        self.stdout.write(self.style.SUCCESS("FAISS index and metadata created successfully!"))
