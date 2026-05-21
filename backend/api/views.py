from django.shortcuts import get_object_or_404, render, redirect
from django.db import transaction
from django.contrib.auth import authenticate, login

from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.authentication import TokenAuthentication, SessionAuthentication
from rest_framework.authtoken.models import Token
from rest_framework import status

from .serializers import *
from .models import User, UserProfile, StudentProfile, InstructorProfile, Course
from .accounts.permission import IsStudent, IsInstructor, IsInstructorOrStudent


# Create your views here.

@api_view(['POST'])
@permission_classes([AllowAny])
@transaction.atomic
def register_user(request):
    user_serializer = UserSerializer(data=request.data)
    if user_serializer.is_valid():
        user = user_serializer.save()
        user.set_password(request.data['password'])
        user.save()

        user_type = request.data.get('user_type', 'student').lower()

        if user_type == 'student':
            UserProfile.objects.create(user=user, user_type='student')
            StudentProfile.objects.create(user=user)
            
        elif user_type == 'instructor':
            InstructorProfile.objects.create(
                user=user,
            )
            UserProfile.objects.create(user=user, user_type='instructor')
        else:
            # Raising an error inside transaction.atomic triggers a rollback
            raise ValueError("Invalid user type provided.")

        token, _ = Token.objects.get_or_create(user=user)
        return Response({'token': token.key, 'user': user_serializer.data}, status=status.HTTP_201_CREATED)
    
    return Response(user_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

def login_page(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return redirect("get_user")  # change this to your dashboard later

        return render(request, "login.html", {
            "error": "Invalid username or password"
        })

    return render(request, "login.html")

@api_view(['POST'])
@permission_classes([AllowAny])
def login_user(request):
    user = get_object_or_404(User, username=request.data['username'])
    if not user.check_password(request.data['password']):
        return Response(status=status.HTTP_401_UNAUTHORIZED)
    token = Token.objects.get(user=user)
    return Response({'token': token.key, 'user': UserSerializer(user).data})



@api_view(['GET', 'PUT', 'DELETE'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated])
def get_user(request):
    user = request.user
    serializer = UserSerializer(user)
    return Response({'user': serializer.data})


@api_view(['GET'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsStudent])
def get_courses(request):
    courses = Course.objects.all()
    serializer = CourseSerializer(courses, many=True)
    return Response({'courses': serializer.data})

@api_view(['POST'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated])
def create_course(request):
    serializer = CourseSerializer(data= request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    

@api_view(['GET', 'PUT', 'DELETE'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructor])
def modify_course(request, pk):
    try:
        course = Course.objects.get(pk=pk)
    except Course.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)
    
    if request.method == 'GET':
        serializer = CourseSerializer(course)
        return Response({'course': serializer.data})
    
    elif request.method == 'PUT':
        serializer = CourseSerializer(course, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        course.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
        

@api_view(['GET'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructor])
def get_students(request):
    return Response({})


@api_view(['GET'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructorOrStudent])
def get_course_materials(request):
    return Response({})


@api_view(['POST'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructor])
def enroll_student(request):
    return Response({})


@api_view(['POST'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructor])
def remove_student(request):
    return Response({})

@api_view(['POST'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructor])
def create_assignment(request):
    return Response({})

@api_view(['POST'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsStudent])
def submit_assignment(request):
    return Response({})

@api_view(['POST'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructor])
def grade_assignment(request): 
    return Response({})

@api_view(['GET'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructorOrStudent])
def get_grades(request):
    return Response({})