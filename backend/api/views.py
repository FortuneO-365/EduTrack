from django.shortcuts import get_object_or_404, render, redirect
from django.db import transaction
from django.db.models import Avg, Max
from django.contrib.auth import authenticate, login, logout
from django.utils import timezone
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.authentication import TokenAuthentication, SessionAuthentication
from rest_framework.authtoken.models import Token
from rest_framework import status
from azure.storage.blob import BlobServiceClient

from .serializers import *
from .models import (
    User,
    UserProfile,
    StudentProfile,
    InstructorProfile,
    Course,
    Enrollment,
    Assignment,
    Materials,
    Submission,
    Notification,
    Scores,
)
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

@api_view(['GET'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsStudent])
def student_dashboard(request):
    user_type = getattr(getattr(request.user, "profile", None), "user_type", None)
    return render(request, "dashboard.html", {"user_type": user_type})

@api_view(['GET'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructor])
def instructor_dashboard(request):

    if not hasattr(request.user, "profile") or request.user.profile.user_type != "instructor":
        return redirect("login_page")

    user_type = "instructor"

    today = timezone.now()

    course = Course.objects.filter(instructor__user=request.user).first()

    if not course:
        return render(request, "dashboard.html", {
            "user_type": user_type,
            "course": None,
            "tutorial_count": 0,
            "active_assignments_count": 0,
            "submission_count": 0,
            "pending_grades_count": 0,
            "last_two_assignments": [],
            "last_three_enrollments": [],
            "last_four_materials": [],
        })

    tutorials = Materials.objects.filter(course=course)
    active_assignments = Assignment.objects.filter(course=course, due_date__gt=today)

    submissions = Submission.objects.filter(
        assignment__in=active_assignments
    ).select_related("student__user")

    pending_grades = submissions.filter(status='submitted')

    last_two_assignments = Assignment.objects.filter(course=course).order_by("-created_at")[:2]
    last_three_enrollments = Enrollment.objects.filter(course=course).order_by("-enrollment_date")[:3]
    last_four_materials = Materials.objects.filter(course=course).order_by("-upload_date")[:4]
    total_students = Enrollment.objects.filter(course=course, status='approved').count()

    return render(request, "dashboard.html", {
        "user_type": user_type,
        "course": course,
        "tutorial_count": tutorials.count(),
        "active_assignments_count": active_assignments.count(),
        "submission_count": submissions.count(),
        "pending_grades_count": pending_grades.count(),
        "last_two_assignments": AssignmentSerializer(last_two_assignments, many=True).data,
        "last_three_enrollments": EnrollmentSerializer(last_three_enrollments, many=True).data,
        "last_four_materials": MaterialsSerializer(last_four_materials, many=True).data,
        "total_students": total_students,
    })

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
        instructor_course = Course.objects.filter(instructor__user=user).first()
        if instructor_course:
            course_serializer = CourseSerializer(instructor_course)
            return render(request, "user_profile.html", {
                "user": serializer.data,
                "user_type": user_type,
                "profile": instructor_serializer.data,
                "course": course_serializer.data
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
    student = StudentProfile.objects.get(user=request.user)

    courses = Course.objects.select_related("instructor__user").all()
    for course in courses:
        course.is_enrolled = Enrollment.objects.filter(
            student=student,
            course=course
        ).exists()

    return render(request, "courses.html", {"courses": courses})
 
@api_view(['GET'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsStudent])
def get_student_courses(request):
    user = request.user.id
    student_id = StudentProfile.objects.get(user__id=user).id
    enrollments = Enrollment.objects.filter(student__id=student_id).select_related('course__instructor__user')
    courses = [enrollment.course for enrollment in enrollments]
    # serializer = CourseSerializer(courses, many=True)
    # return Response({"courses": serializer.data})
    return render(request, "student_courses.html", {"courses": courses})

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

    students_number = len(students)


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
        "user_type": user_type,
        "students_number": students_number
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

@api_view(['GET'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructor])
def get_enrollments(request):

    userId = request.user.id
    user_type = "instructor" 
    instuctorId = InstructorProfile.objects.get(user__id=userId).id
    course_id = Course.objects.get(instructor__id=instuctorId).id

    course = get_object_or_404(Course, id=course_id)

    pending_enrollments = Enrollment.objects.filter(course=course, status='pending').select_related('student__user')
    pending_serializer = EnrollmentSerializer(pending_enrollments, many=True)

    accepted_enrollments = Enrollment.objects.filter(course=course, status='approved').select_related('student__user')
    accepted_serializer = EnrollmentSerializer(accepted_enrollments, many=True)

    # return Response({
    #     "pending_enrollments": pending_serializer.data,
    #     "accepted_enrollments": accepted_serializer.data
    # })
    return render(request, "instructor_enrollments.html", {
        "course": course,
        "user_type": user_type,
        "pending_enrollments": pending_serializer.data,
        "accepted_enrollments": accepted_serializer.data
    })

@api_view(['POST'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsStudent])
def course_enrollment(request, course_id):
    student = get_object_or_404(StudentProfile, user=request.user)
    course = get_object_or_404(Course, id=course_id)
    enrollment, created = Enrollment.objects.get_or_create(student=student, course=course)

    if not created:
        return Response(
            {"message": "You are already enrolled in this course."},
            status=status.HTTP_200_OK,
        )

    notification = Notification.objects.create(
        user=course.instructor.user,
        message=f"{student.user.username} has enrolled in your course {course.title}."
    )

    notification.save()

    return Response(
        {"message": "Course enrolled successfully."},
        status=status.HTTP_201_CREATED,
    )

@api_view(['POST'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructor])
def accept_enrollment(request, enrollment_id):
    enrollment = get_object_or_404(Enrollment, id=enrollment_id)
    enrollment.status = 'approved'
    enrollment.save()

    notification = Notification.objects.create(
        user=enrollment.student.user,
        message=f"Your enrollment in {enrollment.course.title} has been approved."
    )
    notification.save()

    return Response({"message": "Enrollment accepted."}, status=status.HTTP_200_OK)

@api_view(['POST'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructor])
def reject_enrollment(request, enrollment_id):
    enrollment = get_object_or_404(Enrollment, id=enrollment_id)
    enrollment.status = 'rejected'
    enrollment.save()

    notification = Notification.objects.create(
        user=enrollment.student.user,
        message=f"Your enrollment in {enrollment.course.title} has been rejected."
    )
    notification.save()

    enrollment.delete()

    return Response({"message": "Enrollment rejected."}, status=status.HTTP_200_OK)

@api_view(['GET'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructor])
def get_instructor_assignments(request, course_id):
    userId = request.user.id
    user_type = "instructor" 
    instuctorId = InstructorProfile.objects.get(user__id=userId).id

    course = get_object_or_404(Course, id=course_id, instructor__id=instuctorId)

    assignments = Assignment.objects.filter(course=course)
    assignment_serializer = AssignmentSerializer(assignments, many=True)

    enrollments = Enrollment.objects.filter(course=course).select_related('student__user')
    students = [enrollment.student for enrollment in enrollments]
    student_serializer = StudentSerializer(students, many=True)

    return render(request, "instructor_assignments.html", {
        "course": course,
        "assignments": assignment_serializer.data,
        "students": student_serializer.data,
        "user_type": user_type
    })

    # return Response({
    #     "assignments": assignment_serializer.data, 
    #     # "students": student_serializer.data,
    #     "user_type": user_type
    # })

@api_view(['GET'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsStudent])
def get_student_grades(request):

    userId = request.user.id
    studentId = StudentProfile.objects.get(user__id=userId).id

    marked_submissions = Submission.objects.filter(student__id=studentId, status="graded")
    course_ids = Enrollment.objects.filter(student__id=studentId, status='approved').values_list('course_id', flat=True)

    assignments_graded = marked_submissions.count()
    total_assignments = Assignment.objects.filter(course_id__in=course_ids).count()
    
    # Following the OneToOne relationship from Submission to Scores (default related_name is 'scores')
    stats = marked_submissions.aggregate(
        avg_score=Avg('scores__score'),
        max_score=Max('scores__score')
    )

    grades = Scores.objects.filter(submission__student_id=studentId).select_related('submission__assignment')
    serializer = ScoresSerializer(grades, many=True)

    # return Response({
    #     "averageScore": stats['avg_score'] or 0,
    #     "assignmentsGraded": assignments_graded,
    #     "totalAssignments": total_assignments,
    #     "highestScore": stats['max_score'] or 0,
    #     "assignmentList": serializer.data
    # }, status=status.HTTP_200_OK)

    return render(request, "student_grades.html", {
        "averageScore": stats['avg_score'] or 0,
        "assignmentsGraded": assignments_graded,
        "totalAssignments": total_assignments,
        "highestScore": stats['max_score'] or 0,
        "assignmentList": serializer.data
    }, status=status.HTTP_200_OK)

@api_view(['GET'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsStudent])
def get_student_assignments(request):

    userId = request.user.id
    studentId = StudentProfile.objects.get(user__id=userId).id

    course_ids = Enrollment.objects.filter(student__id=studentId, status='approved').values_list('course_id', flat=True)

    total_assignments = Assignment.objects.filter(course_id__in=course_ids).count()
    submitted_assignments = Submission.objects.filter(student__id=studentId).count()
    graded_assignments = Submission.objects.filter(student__id=studentId, status="graded").count()

    pending_assignments = Assignment.objects.filter(
        course_id__in=course_ids
    ).exclude(
        submission__student__id=studentId
    ).distinct().count()

    assignment_list = Assignment.objects.filter(course_id__in=course_ids)
    serializer = AssignmentSerializer(assignment_list, many=True)

    # return Response({
    #     "totalAssignments": total_assignments,
    #     "submittedAssignments": submitted_assignments,
    #     "pendingAssignments": pending_assignments,
    #     "gradedAssignments": graded_assignments,
    #     "assignmentList": serializer.data
    # })

    return render(request, "student_assignments.html", {
        "totalAssignments": total_assignments,
        "submittedAssignments": submitted_assignments,
        "pendingAssignments": pending_assignments,
        "gradedAssignments": graded_assignments,
        "assignmentList": serializer.data
    })

def create_course(request, course_id):

    return render(request, "create_lesson.html", {
        "course_id": course_id
    })


#################  HELPERS  ###################

def redirect_user_by_type(user):
    user_type = getattr(getattr(user, "profile", None), "user_type", None)

    if user_type == "student":
        return redirect("student_dashboard")

    if user_type == "instructor":
        return redirect("instructor_dashboard")

    return redirect("login_page")

def upload_file_to_azure(file_obj, blob_name):
    client = BlobServiceClient.from_connection_string(settings.AZURE_CONNECTION_STRING)
    container = client.get_container_client(settings.AZURE_CONTAINER)

    container.upload_blob(
        name=blob_name,
        data=file_obj.read(),
        overwrite=True
    )

    url = f"https://{settings.AZURE_ACCOUNT_NAME}.blob.core.windows.net/{settings.AZURE_CONTAINER}/{blob_name}"
    return url

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



# @api_view(['POST'])
# @authentication_classes([TokenAuthentication, SessionAuthentication])
# @permission_classes([IsAuthenticated])
# def create_course(request):
#     serializer = CourseSerializer(data= request.data)
#     if serializer.is_valid():
#         serializer.save()
#         return Response(serializer.data)
#     return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    

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
