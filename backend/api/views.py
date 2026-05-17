from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.authentication import TokenAuthentication, SessionAuthentication
from rest_framework.authtoken.models import Token
from rest_framework import status
from .serializers import UserSerializer
from .models import User, UserProfile, StudentProfile, InstructorProfile
from django.shortcuts import get_object_or_404

# Create your views here.

@api_view(['POST'])
@permission_classes([AllowAny])
def register_user(request):
    serializer = UserSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        user = User.objects.get(username=request.data['username'])
        user.set_password(request.data['password'])
        user.save()

        user_type = request.data.get('user_type', 'student')
        UserProfile.objects.create(user=user, user_type=user_type)

        if user_type == 'student':
            StudentProfile.objects.create(user=user)
        elif user_type == 'instructor':
            InstructorProfile.objects.create(user=user)

        token = Token.objects.create(user=user)
        return Response({'token': token.key, 'user': serializer.data})
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([AllowAny])
def login_user(request):
    user = get_object_or_404(User, username=request.data['username'])
    if not user.check_password(request.data['password']):
        return Response(status=status.HTTP_401_UNAUTHORIZED)
    token = Token.objects.get(user=user)
    return Response({'token': token.key, 'user': UserSerializer(user).data})



@api_view(['GET'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated])
def get_user(request):
    user = request.user
    serializer = UserSerializer(user)
    return Response({'user': serializer.data})