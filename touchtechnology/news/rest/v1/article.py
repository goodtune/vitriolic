from rest_framework import serializers

from touchtechnology.news import models

from .viewsets import SlugViewSet


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Category
        fields = ("title", "short_title", "slug", "is_active")


class ListArticleSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Article
        fields = ("headline", "slug", "abstract", "published", "byline", "is_active")


class ArticleSerializer(ListArticleSerializer):
    copy = serializers.CharField(read_only=True)
    keywords = serializers.CharField(read_only=True)
    image = serializers.ImageField(read_only=True)

    class Meta(ListArticleSerializer.Meta):
        fields = ListArticleSerializer.Meta.fields + ("copy", "keywords", "image")


class TranslationSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Translation
        fields = ("headline", "abstract", "copy", "locale")


class CategoryViewSet(SlugViewSet):
    queryset = models.Category.objects.filter(is_active=True)
    serializer_class = CategorySerializer


class ArticleViewSet(SlugViewSet):
    queryset = (
        models.Article.objects.filter(is_active=True)
        .select_related()
        .prefetch_related("categories")
    )
    serializer_class = ArticleSerializer
    list_serializer_class = ListArticleSerializer


class TranslationViewSet(SlugViewSet):
    serializer_class = TranslationSerializer
    lookup_field = "locale"

    def get_queryset(self):
        return models.Translation.objects.filter(
            article__slug=self.kwargs["article_slug"], article__is_active=True
        )
