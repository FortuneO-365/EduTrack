from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.db import transaction
from django.db.models import Avg, Max
from django.contrib.auth import authenticate, login, logout
from django.utils import timezone
from django.conf import settings
from django.core.exceptions import PermissionDenied
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.authentication import TokenAuthentication, SessionAuthentication
from rest_framework.authtoken.models import Token
from rest_framework import status
from azure.storage.blob import BlobServiceClient
from datetime import datetime
import json

from .utils import get_blob_sas_url
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

@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsStudent])
def student_dashboard(request):
    is_authenticated = check_user_authentication(request)
    if not is_authenticated:
        return redirect("login_page")
    
    handle_unauthorized_instructor(request.user)

    user_type = getattr(getattr(request.user, "profile", None), "user_type", None)

    studentId = StudentProfile.objects.get(user__id=request.user.id).id
    courses_enrolled = Enrollment.objects.filter(student__id=studentId)
    assignments = Assignment.objects.filter(course__in=courses_enrolled.values_list('course_id', flat=True))
    submitted_assignments = Submission.objects.filter(student__id=studentId).count()
    avg_score = Scores.objects.filter(submission__student__id=studentId).aggregate(Avg('score'))['score__avg'] or 0
    graded_assignments = Submission.objects.filter(student__id=studentId, status="graded").select_related('assignment')

    graded_assignment_details = []

    for assignment in graded_assignments:        graded_assignment_details.append({
            "title": Assignment.objects.get(id=assignment.assignment_id).title,
            "score": round(Scores.objects.get(submission__id=assignment.id).score),
            "course": Assignment.objects.get(id=assignment.assignment_id).course,
            "instructor": InstructorProfile.objects.get(user__username=Scores.objects.get(submission__id=assignment.id).graded_by).user.get_full_name()
        })


    return render(request, "dashboard.html", {
        "user_type": user_type,
        "course_enrolled": courses_enrolled.count(),
        "all_courses": courses_enrolled,
        "assignments": assignments.count(),
        "submitted_assignments": submitted_assignments,
        "avg_score": round(avg_score),
        "assignment_list": AssignmentSerializer(assignments, many=True).data,
        "graded_assignments": graded_assignment_details,
    })
    
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructor])
def instructor_dashboard(request):

    is_authenticated = check_user_authentication(request)
    if not is_authenticated:
        return redirect("login_page")

    if not hasattr(request.user, "profile") or request.user.profile.user_type != "instructor":
        return redirect("login_page")

    user_type = "instructor"
    today = timezone.now()
    course = Course.objects.filter(instructor__user=request.user).first()
    profile_image= InstructorProfile.objects.filter(user=request.user).values_list('profile_image_url', flat=True).first()

    profile_image_url = get_blob_sas_url(profile_image, expiry_hours=2) if profile_image else None

    if not course:
        return render(request, "dashboard.html", {
            "user_type": user_type,
            "course": None,
            "profile_image_url": profile_image_url,
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

    submissions = Submission.objects.all().select_related("student__user")

    pending_grades = submissions.filter(status='submitted')

    last_two_assignments = Assignment.objects.filter(course=course).order_by("-created_at")[:2]
    last_three_enrollments = Enrollment.objects.filter(course=course).order_by("-enrollment_date")[:3]
    last_four_materials = Materials.objects.filter(course=course).order_by("-upload_date")[:4]
    total_students = Enrollment.objects.filter(course=course, status='approved').count()

    
    return render(request, "dashboard.html", {
        "user_type": user_type,
        "course": course,
        "profile_image_url": profile_image_url,
        "tutorial_count": tutorials.count(),
        "active_assignments_count": active_assignments.count(),
        "submission_count": submissions.count(),
        "pending_grades_count": pending_grades.count(),
        "last_two_assignments": AssignmentSerializer(last_two_assignments, many=True).data,
        "last_three_enrollments": EnrollmentSerializer(last_three_enrollments, many=True).data,
        "last_four_materials": MaterialsSerializer(last_four_materials, many=True).data,
        "total_students": total_students,
        "today": today.strftime("%b %d, %Y - %I:%M %p"),
    })

def logout_view(request):
    logout(request)
    return redirect("login_page")

def get_users(request):
    is_authenticated = check_user_authentication(request)
    if not is_authenticated:
        return redirect("login_page")

    user = User.objects.all()
    serializer = UserSerializer(user, many=True)
    return render(request, "user_profile.html", {"users": serializer.data})

def get_user_profile(request, pk):

    is_authenticated = check_user_authentication(request)
    if not is_authenticated:
        return redirect("login_page")

    user = get_object_or_404(User, pk=pk)
    serializer = UserSerializer(user)
    return render(request, "user_profile.html", {"user": serializer.data})

@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructorOrStudent])
def user_profile(request):
    is_authenticated = check_user_authentication(request)
    if not is_authenticated:
        return redirect("login_page")

    user = request.user
    serializer = UserSerializer(user)
    user_type = getattr(getattr(user, "profile", None), "user_type", None)

    if request.method == 'POST':
        data = request.POST
        uploaded = request.FILES.get('image')

        serializer = UserSerializer(user, data=data, partial=True)
        if not serializer.is_valid():
            return JsonResponse(serializer.errors, status=400)

        serializer.save()

        if uploaded:
            if not uploaded.content_type.startswith('image/'):
                return JsonResponse({"message": "Please upload a valid image file."}, status=400)

            profile = None
            if user_type == "student":
                profile = StudentProfile.objects.get(user=user)
            elif user_type == "instructor":
                profile = InstructorProfile.objects.get(user=user)

            if profile:
                blob_name = f"profile_images/user_{user.id}/{uploaded.name}"
                profile.profile_image_url = upload_file_to_azure(uploaded, blob_name)
                profile.save()

        return JsonResponse({"message": "Profile updated successfully."}, status=200)

    if request.method == 'PUT':
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"message": "Invalid JSON data."}, status=400)

        serializer = UserSerializer(user, data=data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return JsonResponse({"message": "Profile updated successfully."}, status=200)

        return JsonResponse(serializer.errors, status=400)

    if request.method == 'DELETE':
        user.delete()
        logout(request)
        return redirect("login_page")

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

    return render(request, "user_profile.html", {
        "user": serializer.data,
        "user_type": user_type
    })

@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructorOrStudent])
def user_password(request):

    user = request.user
    serializer = UserSerializer(user)
    user_type = getattr(getattr(user, "profile", None), "user_type", None)

    if request.method == 'PUT':
        data = json.loads(request.body)
        oldpassword = data.get('oldpassword')
        newpassword = data.get('newpassword')

        user = authenticate(request, username=user.username, password=oldpassword)
        if user is None:
            return JsonResponse({"message": "Invalid old password."}, status=400)

        user.set_password(newpassword)
        user.save()

        return JsonResponse({"message": "Password updated successfully."}, status=200)
    return render(request, "user_profile.html", {
        "user": serializer.data,
        "user_type": user_type
    })

@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsStudent])
def get_all_courses(request):   
    is_authenticated = check_user_authentication(request)
    if not is_authenticated:
        return redirect("login_page")
    
    handle_unauthorized_instructor(request.user)

    student = StudentProfile.objects.get(user=request.user)

    courses = Course.objects.select_related("instructor__user").all()
    for course in courses:
        course.is_enrolled = Enrollment.objects.filter(
            student=student,
            course=course
        ).exists()

    return render(request, "courses.html", {"courses": courses})
 
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsStudent])
def get_student_courses(request):
    is_authenticated = check_user_authentication(request)
    if not is_authenticated:
        return redirect("login_page")
    
    handle_unauthorized_instructor(request.user)

    user = request.user.id
    student_id = StudentProfile.objects.get(user__id=user).id
    enrollments = Enrollment.objects.filter(student__id=student_id).select_related('course__instructor__user')
    courses = [enrollment.course for enrollment in enrollments]
    # serializer = CourseSerializer(courses, many=True)
    # return Response({"courses": serializer.data})
    return render(request, "student_courses.html", {"courses": courses})

@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructor])
def get_instructor_course(request):
    is_authenticated = check_user_authentication(request)
    if not is_authenticated:
        return redirect("login_page")
    
    handle_unauthorized_student(request.user)

    user = request.user.id
    user_type = "instructor" 
    instructor_id = InstructorProfile.objects.get(user__id=user).id
    today = timezone.now().date().strftime("%b %d, %Y - %I:%M %p")

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

    return render(request, "instructor_class.html", {
        "course": serializer.data,
        "materials": material_serializer.data,
        "assignments": assignment_serializer.data,
        "students": student_serializer.data,
        "user_type": user_type,
        "students_number": students_number,
        "today": today,
    })

@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsStudent])
def get_course_details(request, course_id):
    is_authenticated = check_user_authentication(request)
    if not is_authenticated:
        return redirect("login_page")
    
    handle_unauthorized_instructor(request.user)

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

@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructor])
def get_enrollments(request):
    is_authenticated = check_user_authentication(request)
    if not is_authenticated:
        return redirect("login_page")
    
    handle_unauthorized_student(request.user)

    userId = request.user.id
    user_type = "instructor" 
    instuctorId = InstructorProfile.objects.get(user__id=userId).id
    course_id = Course.objects.get(instructor__id=instuctorId).id

    course = get_object_or_404(Course, id=course_id)

    pending_enrollments = Enrollment.objects.filter(course=course, status='pending').select_related('student__user')
    pending_serializer = EnrollmentSerializer(pending_enrollments, many=True)

    accepted_enrollments = Enrollment.objects.filter(course=course, status='approved').select_related('student__user')
    accepted_serializer = EnrollmentSerializer(accepted_enrollments, many=True)

    return render(request, "instructor_enrollments.html", {
        "course": course,
        "user_type": user_type,
        "pending_enrollments": pending_serializer.data,
        "accepted_enrollments": accepted_serializer.data
    })

@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsStudent])
def course_enrollment(request, course_id):
    is_authenticated = check_user_authentication(request)
    if not is_authenticated:
        return redirect("login_page")
    
    handle_unauthorized_instructor(request.user)

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

@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructor])
def accept_enrollment(request, enrollment_id):
    is_authenticated = check_user_authentication(request)
    if not is_authenticated:
        return redirect("login_page")
    
    handle_unauthorized_student(request.user)

    enrollment = get_object_or_404(Enrollment, id=enrollment_id)
    enrollment.status = 'approved'
    enrollment.save()

    notification = Notification.objects.create(
        user=enrollment.student.user,
        message=f"Your enrollment in {enrollment.course.title} has been approved."
    )
    notification.save()

    return Response({"message": "Enrollment accepted."}, status=status.HTTP_200_OK)

@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructor])
def reject_enrollment(request, enrollment_id):
    is_authenticated = check_user_authentication(request)
    if not is_authenticated:
        return redirect("login_page")

    handle_unauthorized_student(request.user)

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

@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructor])
def get_instructor_assignments(request, course_id):
    is_authenticated = check_user_authentication(request)
    if not is_authenticated:
        return redirect("login_page")
    
    handle_unauthorized_student(request.user)

    userId = request.user.id
    user_type = "instructor" 
    today = timezone.now().date().strftime("%b %d, %Y - %I:%M %p")
    instuctorId = InstructorProfile.objects.get(user__id=userId).id

    course = get_object_or_404(Course, id=course_id, instructor__id=instuctorId)

    assignments = Assignment.objects.filter(course=course)
    assignment_serializer = AssignmentSerializer(assignments, many=True)

    assignment_array = []

    enrollments = Enrollment.objects.filter(course=course).select_related('student__user')
    students = [enrollment.student for enrollment in enrollments]
    student_serializer = StudentSerializer(students, many=True)

    for assignment in assignments:
        submission_count = Submission.objects.filter(assignment=assignment).count()

        assignment_array.append({
            "assignment": AssignmentSerializer(assignment).data,
            "submission_count": submission_count,
        })

    return render(request, "instructor_assignments.html", {
        "course": course,
        "assignments": assignment_serializer.data,
        "total_students": enrollments.count(),
        "students": student_serializer.data,
        "user_type": user_type,
        "assignment_stats": assignment_array,
        "today": today,
    })

@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsStudent])
def get_student_grades(request):
    is_authenticated = check_user_authentication(request)
    if not is_authenticated:
        return redirect("login_page")

    handle_unauthorized_instructor(request.user)

    user_id = request.user.id
    student = StudentProfile.objects.get(user_id=user_id)

    course_ids = Enrollment.objects.filter(
        student=student,
        status="approved"
    ).values_list("course_id", flat=True)

    assignments = Assignment.objects.filter(
        course_id__in=course_ids
    ).select_related("course")

    marked_submissions = Submission.objects.filter(
        student=student,
        status="graded"
    )

    stats = marked_submissions.aggregate(
        avg_score=Avg("scores__score"),
        max_score=Max("scores__score")
    )

    marked_submissions_list = []

    for submission in marked_submissions:
        marked_submissions_list.append({
            "title": submission.assignment.title,
            "score": round(Scores.objects.get(submission=submission).score),
            "course": Course.objects.get(id=submission.assignment.course_id).title,
        })

    return render(
        request,
        "student_grades.html",
        {
            "averageScore": round(stats["avg_score"]) or 0,
            "assignmentsGraded": marked_submissions.count(),
            "totalAssignments": assignments.count(),
            "highestScore": round(stats["max_score"]) or 0,
            "assignmentList": AssignmentSerializer(assignments, many=True).data,
            "markedSubmissions": marked_submissions_list
        },
    )

@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsStudent])
def get_student_assignments(request):
    is_authenticated = check_user_authentication(request)
    if not is_authenticated:
        return redirect("login_page")
    
    handle_unauthorized_instructor(request.user)

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

    assignments = Assignment.objects.filter(course_id__in=course_ids)
    assignment_list = []

    for assignment in assignments:
        submission = Submission.objects.filter(
            assignment=assignment,
            student__id=studentId
        ).first()

        # Format due_date for template rendering
        due_date_formatted = assignment.due_date.strftime("%b %d, %Y - %I:%M %p") if assignment.due_date else None

        assignment_list.append({
            "id": assignment.id,
            "title": assignment.title,
            "description": assignment.description,
            "due_date": due_date_formatted,
            "course_name": assignment.course.title,
            "submitted": submission is not None,
            "graded": submission and submission.status == "graded",
            "submission_id": submission.id if submission else None,
        })

    return render(request, "student_assignments.html", {
        "totalAssignments": total_assignments,
        "submittedAssignments": submitted_assignments,
        "pendingAssignments": pending_assignments,
        "gradedAssignments": graded_assignments,
        "assignmentList": assignment_list
    })

@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructor])
def create_course_material(request, course_id):
    is_authenticated = check_user_authentication(request)
    if not is_authenticated:
        return redirect("login_page")
    
    handle_unauthorized_student(request.user)
    if request.method == 'POST':
        course = get_object_or_404(Course, id=course_id)

        title = request.POST.get('title')
        description = request.POST.get('description')
        uploaded = request.FILES.get('file')

        if not title or not description or not uploaded:
            return JsonResponse(
                {"message": "Please provide a title, description, and file."},
                status=400,
            )

        blob_name = f"course_{course_id}/{uploaded.name}"
        file_url = upload_file_to_azure(uploaded, blob_name)
        file_name = uploaded.name
        print(uploaded.content_type)


        Materials.objects.create(
            course=course,
            uploaded_by=course.instructor,
            title=title,
            description=description,
            file_name=file_name,
            file_url=file_url,
            file_type=uploaded.content_type,
        )

        return JsonResponse(
            {"message": "Lesson published successfully."},
            status=201,
        )

    return render(request, "create_lesson.html", {
        "course_id": course_id
    })


@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructorOrStudent])
def view_course_material(request, material_id):
    is_authenticated = check_user_authentication(request)
    if not is_authenticated:
        return redirect("login_page")

    topic = get_object_or_404(Materials, id=material_id)
    topic_material = get_blob_sas_url(topic.file_url, expiry_hours=2) if topic.file_url else None

    serializer = MaterialsSerializer(topic)

    return JsonResponse(
        {
            "material": serializer.data,
            "material_url": topic_material
        },
        status=200,
    )

@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructor])
def modify_course_material(request, material_id):
    is_authenticated = check_user_authentication(request)
    if not is_authenticated:
        return redirect("login_page")

    handle_unauthorized_student(request.user)

    material = get_object_or_404(Materials, id=material_id)

    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description')
        file_name = request.POST.get('file_name')
        uploaded = request.FILES.get('file')



        if title:
            material.title = title
        if description:
            material.description = description
        if uploaded:
            blob_name = f"course_{material.course.id}/{uploaded.name}"
            material.file_url = upload_file_to_azure(uploaded, blob_name)
            material.file_type = uploaded.content_type
            material.file_name = file_name

        material.save()

        return JsonResponse(
            {"message": "Material updated successfully."},
            status=200,
        )

    elif request.method == 'DELETE':
        material.delete()
        return JsonResponse(
            {"message": "Material deleted successfully."},
            status=200,
        )

    return render(request, "instructor_class.html", {
        "material_id": material_id,
        "material": material
    })

@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructor])
def create_assignment(request, course_id):

    is_authenticated = check_user_authentication(request)
    if not is_authenticated:
        return redirect("login_page")

    handle_unauthorized_student(request.user)

    course = get_object_or_404(Course, id=course_id)

    if request.method == 'POST':
        try:
            data = json.loads(request.body.decode('utf-8'))
        except json.JSONDecodeError:
            return JsonResponse(
                {"message": "Invalid JSON"},
                status=400
            )
        title = data.get('title')
        description = data.get('description')
        due_date_str = data.get('due_date')

        if not title or not description or not due_date_str:
            return JsonResponse(
                {"message": "Please provide a title, description, and due date."},
                status=400,
            )
        
        # Parse the datetime string and make it timezone-aware
        due_date = datetime.fromisoformat(due_date_str.replace('Z', '+00:00'))
        if due_date.tzinfo is None:
            due_date = timezone.make_aware(due_date)
        
        assignment = Assignment.objects.create(
            course_id=course_id,
            title=title,
            description=description,
            due_date=due_date,
        )

        return JsonResponse(
            {"message": "Assignment created successfully.", "assignment_id": assignment.id},
            status=201,
        )

    return JsonResponse(
        {"course": CourseSerializer(course).data},
        status=200,
    )

@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructor])
def modify_assignment(request, assignment_id):
    is_authenticated = check_user_authentication(request)
    if not is_authenticated:
        return redirect("login_page")

    handle_unauthorized_student(request.user)

    assignment = get_object_or_404(Assignment, id=assignment_id)

    if request.method == 'PUT':
        data = json.loads(request.body.decode('utf-8'))
        title = data.get('title')
        description = data.get('description')
        due_date_str = data.get('due_date')

        if title:
            assignment.title = title
        if description:
            assignment.description = description
        if due_date_str:
            from datetime import datetime
            due_date = datetime.fromisoformat(due_date_str.replace('Z', '+00:00'))
            if due_date.tzinfo is None:
                due_date = timezone.make_aware(due_date)
            assignment.due_date = due_date

        assignment.save()

        return JsonResponse(
            {"message": "Assignment updated successfully."},
            status=200,
        )
    elif request.method == 'DELETE':
        assignment.delete()
        return JsonResponse(
            {"message": "Assignment deleted successfully."},
            status=200,
        )

    return render(request, "instructor_assignments.html", {
        "assignment_id": assignment_id,
        "assignment": assignment
    })

@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructorOrStudent])
def get_assignment_details(request, assignment_id):
    is_authenticated = check_user_authentication(request)
    if not is_authenticated:
        return redirect("login_page")

    if request.user.profile.user_type == "student":
        assignment = get_object_or_404(Assignment, id=assignment_id)
        serializer = AssignmentSerializer(assignment)

        return JsonResponse(
            {"assignment": serializer.data},
            status=200,
        )
    elif request.user.profile.user_type == "instructor":
        assignment = get_object_or_404(Assignment, id=assignment_id)
        date_format = assignment.due_date.isoformat()
        serializer = AssignmentSerializer(assignment)

        submissions = Submission.objects.filter(assignment=assignment).select_related('student__user')
        submission_serializer = SubmissionSerializer(submissions, many=True)

        return JsonResponse(
            {
                "assignment": serializer.data,
                "submissions": submission_serializer.data,
                "due_date": date_format,
            },
            status=200,
        )

@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsStudent])
def submit_assignment(request, assignment_id):
    is_authenticated = check_user_authentication(request)
    if not is_authenticated:
        return redirect("login_page")

    handle_unauthorized_instructor(request.user)

    assignment = get_object_or_404(Assignment, id=assignment_id)
    today = timezone.now().date().strftime("%b %d, %Y - %I:%M %p")

    if(today > assignment.due_date):
        return JsonResponse(
            {"message": "Assignment has passed due date."},
            status=400,
        )
    
    student = get_object_or_404(StudentProfile, user=request.user)

    if request.method == 'POST':
        uploaded = request.FILES.get('file')

        if not uploaded:
            return JsonResponse(
                {"message": "Please upload a file."},
                status=400,
            )

        blob_name = f"submissions/assignment_{assignment_id}/student_{student.id}/{uploaded.name}"
        file_url = upload_file_to_azure(uploaded, blob_name)

        submission, created = Submission.objects.get_or_create(
            assignment=assignment,
            student=student,
            defaults={
                "file_url": file_url,
                "file_name": uploaded.name,
                "status": "submitted"
            }
        )
        if not created:
            submission.file_url = file_url
            submission.file_type = uploaded.content_type
            submission.file_name = uploaded.name
            submission.status = "submitted"
            submission.save()

        return JsonResponse(
            {"message": "Assignment submitted successfully."},
            status=201,
        )

    return JsonResponse(
        {"assignment": AssignmentSerializer(assignment).data},
        status=200,
    )

@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructor])
def get_submissions(request, assignment_id):
    is_authenticated = check_user_authentication(request)
    if not is_authenticated:
        return redirect("login_page")

    handle_unauthorized_student(request.user)

    assignment = get_object_or_404(Assignment, id=assignment_id)
    assignment_id = AssignmentSerializer(assignment).data["id"]
    submissions = Submission.objects.filter(assignment=assignment_id).select_related('student__user')
    submission_details = []

    for submission in submissions:

        submission_details.append({
            "id": submission.id,
            "assignment": submission.assignment.id,
            "student": StudentProfile.objects.get(id=submission.student.id).user.get_full_name(),
            "file_url": get_blob_sas_url(submission.file_url, expiry_hours=2) if submission.file_url else None,
            "file_name": submission.file_name,
            "status": submission.status,
            "submitted_at":  submission.submission_date.strftime("%b %d, %Y - %I:%M %p") if submission.submission_date else None
        })

    return JsonResponse(
        {"submissions": submission_details},
        status=200,
    )

@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructor])
def get_submission_details(request, submission_id, assignment_id):
    is_authenticated = check_user_authentication(request)
    if not is_authenticated:
        return redirect("login_page")

    handle_unauthorized_student(request.user)

    submission = get_object_or_404(Submission, id=submission_id, assignment__id=assignment_id)
    submission_serializer = SubmissionSerializer(submission)

    return JsonResponse(
        {"submission": submission_serializer.data},
        status=200,
    )
    
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructor])    
def grade_submission(request, submission_id, assignment_id):
    is_authenticated = check_user_authentication(request)
    if not is_authenticated:
        return redirect("login_page")

    handle_unauthorized_student(request.user)

    if request.method == 'POST':
        data = json.loads(request.body.decode('utf-8'))

        score = data.get('score')
        feedback = data.get('feedback')

        if not score or not feedback:
            return JsonResponse(
                {"message": "Please provide a score and feedback."},
                status=400,
            )

        instructor = InstructorProfile.objects.get(user__id=request.user.id)

        submission = get_object_or_404(Submission, id=submission_id)
        submission.status = "graded"
        submission.save()

        score = Scores.objects.create(submission=submission ,graded_by=instructor, score=score, feedback=feedback)
        score.save()

        return JsonResponse(
            {"message": "Submission graded successfully."},
            status=200,
        )


    return JsonResponse(
        {"message": "Invalid request method."},
        status=405,
    )

        

#################  HELPERS  ###################
def check_user_authentication(request):
    if not request.user.is_authenticated:
        return False
    return True
        
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

def handle_unauthorized_student(user):
    if user.profile.user_type != "instructor":
        raise PermissionDenied("You do not have permission to access this resource.")
    
def handle_unauthorized_instructor(user):
    if user.profile.user_type != "student":
        raise PermissionDenied("You do not have permission to access this resource.")
