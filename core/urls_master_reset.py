from django.urls import path
from . import views_master_reset

urlpatterns = [
    path('master-reset/', views_master_reset.master_reset_view, name='master_reset'),
    path('regenerate-master-code/', views_master_reset.regenerate_master_code_view, name='regenerate_master_code'),
]
