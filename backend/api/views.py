from django.shortcuts import get_object_or_404, render, redirect
from django.db import transaction
from django.contrib.auth import authenticate, login, logout

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

#################  PAGES  ###################
def login_page(request):
    if request.user.is_authenticated:
        return redirect_user_by_type(request.user)

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return redirect_user_by_type(user)

        return render(request, "login.html", {
            "error": "Invalid username or password",
            "username": username,
        })

    return render(request, "login.html")


def redirect_user_by_type(user):
    user_type = getattr(getattr(user, "profile", None), "user_type", None)

    if user_type == "student":
        return redirect("student_dashboard")

    if user_type == "instructor":
        return redirect("instructor_dashboard")

    return redirect("login_page")

@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsStudent])
def student_dashboard(request):
    user_type = getattr(getattr(request.user, "profile", None), "user_type", None)
    return render(request, "dashboard.html", {"user_type": user_type})

@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructor])
def instructor_dashboard(request):
    user_type = getattr(getattr(request.user, "profile", None), "user_type", None)
    return render(request, "dashboard.html", {"user_type": user_type})


def logout_view(request):
    logout(request)
    return redirect("login_page")

def get_users(request):
    user = User.objects.all()
    serializer = UserSerializer(user, many=True)
    return render(request, "user_profile.html", {"users": serializer.data})

def get_user_profile(request, pk):
    user = get_object_or_404(User, pk=pk)
    serializer = UserSerializer(user)
    return render(request, "user_profile.html", {"user": serializer.data})

@api_view(['GET', 'PUT', 'DELETE'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructorOrStudent])
def user_profile(request):
    user = request.user
    serializer = UserSerializer(user)
    user_type = getattr(getattr(user, "profile", None), "user_type", None)

    if user_type == "student":
        student_details = StudentProfile.objects.get(user=user)
        student_serializer = StudentSerializer(student_details)
        return render(
            request, 
            "user_profile.html", 
            {
                "user": serializer.data,
                "user_type": user_type,
                "profile": student_serializer.data
            })

    elif user_type == "instructor":
        instructor_details = InstructorProfile.objects.get(user=user)
        instructor_serializer = InstructorSerializer(instructor_details)
        return render(
            request, 
            "user_profile.html", 
            {
                "user": serializer.data,
                "user_type": user_type,
                "profile": instructor_serializer.data
            })
    
    if request.method == 'PUT':
        serializer = UserSerializer(user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return render(
                request,
                'user_profile.html',
                {
                    "user":  serializer.data
                })
        else:
            return render(
                request,
                'user_profile.html',
                {
                    "error": serializer.errors,
                    "user": serializer.data
                })
        
    elif request.method == 'DELETE':
        user.delete()
        logout(request)
        return redirect("login_page")
    
    return render(
        request, 
        "user_profile.html", 
        {
            "user": serializer.data,
            "user_type": user_type
        })
    

@api_view(['GET'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsStudent])
def get_all_courses(request):
    # courses = Course.objects.all()
    # serializer = CourseSerializer(courses, many=True)
    courses = Course.objects.select_related("instructor__user").all()
    return render(request, "courses.html", {"courses": courses})
    # return Response({"courses": courses})   
 
@api_view(['GET'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsStudent])
def get_student_courses(request):
    user = request.user.id
    student_id = StudentProfile.objects.get(user__id=user).id
    enrollments = Enrollment.objects.filter(student__id=student_id).select_related('course__instructor__user')
    courses = [enrollment.course for enrollment in enrollments]
    serializer = CourseSerializer(courses, many=True)
    # return Response({"courses": serializer.data})
    return render(request, "student_courses.html", {"courses": serializer.data})

@api_view(['GET'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructor])
def get_instructor_course(request):
    user = request.user.id
    user_type = "instructor" 
    instructor_id = InstructorProfile.objects.get(user__id=user).id

    course = Course.objects.filter(instructor__id=instructor_id)
    serializer = CourseSerializer(course, many=True)

    course_materials = Materials.objects.filter(course__in=course)
    material_serializer = MaterialsSerializer(course_materials, many=True)

    assignments = Assignment.objects.filter(course__in=course)
    assignment_serializer = AssignmentSerializer(assignments, many=True)

    enrollments = Enrollment.objects.filter(course__in=course).select_related('student__user')
    students = [enrollment.student for enrollment in enrollments]
    student_serializer = StudentSerializer(students, many=True)


    # return Response({
    #     "courses": serializer.data,
    #     "materials": material_serializer.data,
    #     "assignments": assignment_serializer.data,
    #     "students": student_serializer.data
    # })

    return render(request, "instructor_class.html", {
        "course": serializer.data,
        "materials": material_serializer.data,
        "assignments": assignment_serializer.data,
        "students": student_serializer.data,
        "user_type": user_type
    })

@api_view(['GET'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsStudent])
def get_course_details(request, course_id):

    course = get_object_or_404(Course.objects.select_related("instructor__user"), id=course_id)
    is_enrolled = Enrollment.objects.filter(student__user=request.user, course=course).exists()

    course_materials = Materials.objects.filter(course=course) if is_enrolled else []
    assignments = Assignment.objects.filter(course=course) if is_enrolled else []

    return render(request, "course_details.html", {
        "course": course,
        "materials": course_materials,
        "assignments": assignments,
        "is_enrolled": is_enrolled,
        "user_type": "student",
    })


#################  ENDPOINTS  ###################


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

#to be removed later, just for testing purposes
@api_view(['POST'])
@permission_classes([AllowAny])
def login_user(request):
    user = get_object_or_404(User, username=request.data['username'])
    if not user.check_password(request.data['password']):
        return Response(status=status.HTTP_401_UNAUTHORIZED)
    token = Token.objects.get(user=user)
    return Response({'token': token.key, 'user': UserSerializer(user).data})



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
