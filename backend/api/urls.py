from django.urls import path
from .views import get_user, register_user, login_user

urlpatterns = [
    path('users/', get_user, name='get_user'),
    path('auth/register/', register_user, name='register'),
    path('auth/login/', login_user, name='login')
]