from django.db import models
from django.utils.text import slugify


class PublicPageQuerySet(models.QuerySet):
    def for_agency(self, agency):
        return self.filter(agency=agency)

    def published(self):
        return self.filter(is_published=True)

    def in_nav(self):
        return self.filter(is_published=True, show_in_nav=True).order_by("nav_order", "title")

    def legal(self):
        return self.filter(
            is_published=True, show_in_nav=False,
            template_variant="legal",
        ).order_by("nav_order", "title")


class PublicPage(models.Model):
    TEMPLATE_CHOICES = [
        ("default", "Par défaut"),
        ("about", "À propos"),
        ("faq", "FAQ"),
        ("contact", "Contact"),
        ("legal", "Mentions légales"),
        ("promo", "Promo / Landing"),
    ]

    agency = models.ForeignKey(
        "agencies.Agency",
        on_delete=models.CASCADE,
        related_name="public_pages",
    )
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200)
    content = models.TextField(blank=True, default="")
    is_published = models.BooleanField(default=False)
    show_in_nav = models.BooleanField(default=False)
    nav_order = models.PositiveIntegerField(default=0)
    template_variant = models.CharField(
        max_length=20, choices=TEMPLATE_CHOICES, default="default",
    )
    cta_label = models.CharField(max_length=100, blank=True, default="")
    cta_url = models.CharField(max_length=500, blank=True, default="")
    seo_title = models.CharField(max_length=200, blank=True, default="")
    seo_description = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = PublicPageQuerySet.as_manager()

    class Meta:
        ordering = ["nav_order", "title"]
        unique_together = [("agency", "slug")]
        verbose_name = "Page publique"
        verbose_name_plural = "Pages publiques"

    def __str__(self):
        return f"{self.title} ({self.agency.slug})"

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title) or "page"
            slug = base
            i = 1
            while PublicPage.objects.filter(agency=self.agency, slug=slug).exclude(pk=self.pk).exists():
                i += 1
                slug = f"{base}-{i}"
            self.slug = slug
        super().save(*args, **kwargs)
