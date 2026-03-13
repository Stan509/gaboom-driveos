from django.shortcuts import render
from .models import GalleryProject


def portfolio_es(request):
    projects = GalleryProject.objects.all()
    return render(request, 'portfolio/es/portfolio.html', {'projects': projects})
