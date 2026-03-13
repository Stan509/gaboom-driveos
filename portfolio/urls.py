from django.urls import path
from . import views

urlpatterns = [
    path('es/portfolio/', views.portfolio_es, name='portfolio_es'),
]
