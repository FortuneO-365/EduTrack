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
import logging

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

logger = logging.getLogger(__name__)


# Create your views here.

#################  PAGES  ###################

def login_page(request):
    try:
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
    except Exception as e:
        logger.error(f"[login_page] Unexpected error: {e}", exc_info=True)
        return render(request, "login.html", {"error": "An unexpected error occurred. Please try again."})


@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsStudent])
def student_dashboard(request):
    try:
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

        for assignment in graded_assignments:
            graded_assignment_details.append({
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
    except StudentProfile.DoesNotExist:
        logger.error(f"[student_dashboard] StudentProfile not found for user {request.user.id}")
        return redirect("login_page")
    except Exception as e:
        logger.error(f"[student_dashboard] Unexpected error: {e}", exc_info=True)
        return JsonResponse({"error": "Failed to load student dashboard.", "detail": str(e)}, status=500)


@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructor])
def instructor_dashboard(request):
    try:
        is_authenticated = check_user_authentication(request)
        if not is_authenticated:
            return redirect("login_page")

        if not hasattr(request.user, "profile") or request.user.profile.user_type != "instructor":
            return redirect("login_page")

        user_type = "instructor"
        today = timezone.now()
        course = Course.objects.filter(instructor__user=request.user).first()
        profile_image = InstructorProfile.objects.filter(user=request.user).values_list('profile_image_url', flat=True).first()
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
    except InstructorProfile.DoesNotExist:
        logger.error(f"[instructor_dashboard] InstructorProfile not found for user {request.user.id}")
        return redirect("login_page")
    except Exception as e:
        logger.error(f"[instructor_dashboard] Unexpected error: {e}", exc_info=True)
        return JsonResponse({"error": "Failed to load instructor dashboard.", "detail": str(e)}, status=500)


def logout_view(request):
    try:
        logout(request)
        return redirect("login_page")
    except Exception as e:
        logger.error(f"[logout_view] Unexpected error: {e}", exc_info=True)
        return redirect("login_page")


def get_users(request):
    try:
        is_authenticated = check_user_authentication(request)
        if not is_authenticated:
            return redirect("login_page")

        user = User.objects.all()
        serializer = UserSerializer(user, many=True)
        return render(request, "user_profile.html", {"users": serializer.data})
    except Exception as e:
        logger.error(f"[get_users] Unexpected error: {e}", exc_info=True)
        return JsonResponse({"error": "Failed to retrieve users.", "detail": str(e)}, status=500)


def get_user_profile(request, pk):
    try:
        is_authenticated = check_user_authentication(request)
        if not is_authenticated:
            return redirect("login_page")

        user = get_object_or_404(User, pk=pk)
        serializer = UserSerializer(user)
        return render(request, "user_profile.html", {"user": serializer.data})
    except Exception as e:
        logger.error(f"[get_user_profile] Unexpected error for pk={pk}: {e}", exc_info=True)
        return JsonResponse({"error": "Failed to retrieve user profile.", "detail": str(e)}, status=500)


@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructorOrStudent])
def user_profile(request):
    try:
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
            return render(request, "user_profile.html", {
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
    except Exception as e:
        logger.error(f"[user_profile] Unexpected error for user {request.user.id}: {e}", exc_info=True)
        return JsonResponse({"error": "Failed to process profile request.", "detail": str(e)}, status=500)


@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructorOrStudent])
def user_password(request):
    try:
        user = request.user
        serializer = UserSerializer(user)
        user_type = getattr(getattr(user, "profile", None), "user_type", None)

        if request.method == 'PUT':
            try:
                data = json.loads(request.body)
            except json.JSONDecodeError:
                return JsonResponse({"message": "Invalid JSON data."}, status=400)

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
    except Exception as e:
        logger.error(f"[user_password] Unexpected error for user {request.user.id}: {e}", exc_info=True)
        return JsonResponse({"error": "Failed to update password.", "detail": str(e)}, status=500)


@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsStudent])
def get_all_courses(request):
    try:
        is_authenticated = check_user_authentication(request)
        if not is_authenticated:
            return redirect("login_page")

        handle_unauthorized_instructor(request.user)

        student = StudentProfile.objects.get(user=request.user)
        courses = Course.objects.select_related("instructor__user").all()
        for course in courses:
            course.is_enrolled = Enrollment.objects.filter(student=student, course=course).exists()

        return render(request, "courses.html", {"courses": courses})
    except StudentProfile.DoesNotExist:
        logger.error(f"[get_all_courses] StudentProfile not found for user {request.user.id}")
        return redirect("login_page")
    except Exception as e:
        logger.error(f"[get_all_courses] Unexpected error: {e}", exc_info=True)
        return JsonResponse({"error": "Failed to retrieve courses.", "detail": str(e)}, status=500)


@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsStudent])
def get_student_courses(request):
    try:
        is_authenticated = check_user_authentication(request)
        if not is_authenticated:
            return redirect("login_page")

        handle_unauthorized_instructor(request.user)

        user = request.user.id
        student_id = StudentProfile.objects.get(user__id=user).id
        enrollments = Enrollment.objects.filter(student__id=student_id).select_related('course__instructor__user')
        courses = [enrollment.course for enrollment in enrollments]
        return render(request, "student_courses.html", {"courses": courses})
    except StudentProfile.DoesNotExist:
        logger.error(f"[get_student_courses] StudentProfile not found for user {request.user.id}")
        return redirect("login_page")
    except Exception as e:
        logger.error(f"[get_student_courses] Unexpected error: {e}", exc_info=True)
        return JsonResponse({"error": "Failed to retrieve student courses.", "detail": str(e)}, status=500)


@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructor])
def get_instructor_course(request):
    try:
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

        return render(request, "instructor_class.html", {
            "course": serializer.data,
            "materials": material_serializer.data,
            "assignments": assignment_serializer.data,
            "students": student_serializer.data,
            "user_type": user_type,
            "students_number": len(students),
            "today": today,
        })
    except InstructorProfile.DoesNotExist:
        logger.error(f"[get_instructor_course] InstructorProfile not found for user {request.user.id}")
        return redirect("login_page")
    except Exception as e:
        logger.error(f"[get_instructor_course] Unexpected error: {e}", exc_info=True)
        return JsonResponse({"error": "Failed to retrieve instructor course.", "detail": str(e)}, status=500)


@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsStudent])
def get_course_details(request, course_id):
    try:
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
    except Exception as e:
        logger.error(f"[get_course_details] Unexpected error for course_id={course_id}: {e}", exc_info=True)
        return JsonResponse({"error": "Failed to retrieve course details.", "detail": str(e)}, status=500)


@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructor])
def get_enrollments(request):
    try:
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
        accepted_enrollments = Enrollment.objects.filter(course=course, status='approved').select_related('student__user')

        return render(request, "instructor_enrollments.html", {
            "course": course,
            "user_type": user_type,
            "pending_enrollments": EnrollmentSerializer(pending_enrollments, many=True).data,
            "accepted_enrollments": EnrollmentSerializer(accepted_enrollments, many=True).data,
        })
    except InstructorProfile.DoesNotExist:
        logger.error(f"[get_enrollments] InstructorProfile not found for user {request.user.id}")
        return JsonResponse({"error": "Instructor profile not found."}, status=404)
    except Course.DoesNotExist:
        logger.error(f"[get_enrollments] No course found for instructor {request.user.id}")
        return JsonResponse({"error": "No course found for this instructor."}, status=404)
    except Exception as e:
        logger.error(f"[get_enrollments] Unexpected error: {e}", exc_info=True)
        return JsonResponse({"error": "Failed to retrieve enrollments.", "detail": str(e)}, status=500)


@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsStudent])
def course_enrollment(request, course_id):
    try:
        is_authenticated = check_user_authentication(request)
        if not is_authenticated:
            return redirect("login_page")

        handle_unauthorized_instructor(request.user)

        student = get_object_or_404(StudentProfile, user=request.user)
        course = get_object_or_404(Course, id=course_id)
        enrollment, created = Enrollment.objects.get_or_create(student=student, course=course)

        if not created:
            return JsonResponse({"message": "You are already enrolled in this course."}, status=status.HTTP_200_OK)

        Notification.objects.create(
            user=course.instructor.user,
            message=f"{student.user.username} has enrolled in your course {course.title}."
        )

        return JsonResponse({"message": "Course enrolled successfully."}, status=status.HTTP_201_CREATED)
    except Exception as e:
        logger.error(f"[course_enrollment] Unexpected error for course_id={course_id}: {e}", exc_info=True)
        return JsonResponse({"error": "Failed to enroll in course.", "detail": str(e)}, status=500)


@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructor])
def accept_enrollment(request, enrollment_id):
    try:
        is_authenticated = check_user_authentication(request)
        if not is_authenticated:
            return redirect("login_page")

        handle_unauthorized_student(request.user)

        enrollment = get_object_or_404(Enrollment, id=enrollment_id)
        enrollment.status = 'approved'
        enrollment.save()

        Notification.objects.create(
            user=enrollment.student.user,
            message=f"Your enrollment in {enrollment.course.title} has been approved."
        )

        return JsonResponse({"message": "Enrollment accepted."}, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"[accept_enrollment] Unexpected error for enrollment_id={enrollment_id}: {e}", exc_info=True)
        return JsonResponse({"error": "Failed to accept enrollment.", "detail": str(e)}, status=500)


@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructor])
def reject_enrollment(request, enrollment_id):
    try:
        is_authenticated = check_user_authentication(request)
        if not is_authenticated:
            return redirect("login_page")

        handle_unauthorized_student(request.user)

        enrollment = get_object_or_404(Enrollment, id=enrollment_id)
        enrollment.status = 'rejected'
        enrollment.save()

        Notification.objects.create(
            user=enrollment.student.user,
            message=f"Your enrollment in {enrollment.course.title} has been rejected."
        )

        enrollment.delete()
        return JsonResponse({"message": "Enrollment rejected."}, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"[reject_enrollment] Unexpected error for enrollment_id={enrollment_id}: {e}", exc_info=True)
        return JsonResponse({"error": "Failed to reject enrollment.", "detail": str(e)}, status=500)


@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructor])
def get_instructor_assignments(request, course_id):
    try:
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
        enrollments = Enrollment.objects.filter(course=course).select_related('student__user')
        students = [enrollment.student for enrollment in enrollments]

        assignment_array = []
        for assignment in assignments:
            assignment_array.append({
                "assignment": AssignmentSerializer(assignment).data,
                "submission_count": Submission.objects.filter(assignment=assignment).count(),
            })

        return render(request, "instructor_assignments.html", {
            "course": course,
            "assignments": AssignmentSerializer(assignments, many=True).data,
            "total_students": enrollments.count(),
            "students": StudentSerializer(students, many=True).data,
            "user_type": user_type,
            "assignment_stats": assignment_array,
            "today": today,
        })
    except InstructorProfile.DoesNotExist:
        logger.error(f"[get_instructor_assignments] InstructorProfile not found for user {request.user.id}")
        return JsonResponse({"error": "Instructor profile not found."}, status=404)
    except Exception as e:
        logger.error(f"[get_instructor_assignments] Unexpected error for course_id={course_id}: {e}", exc_info=True)
        return JsonResponse({"error": "Failed to retrieve assignments.", "detail": str(e)}, status=500)


@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsStudent])
def get_student_grades(request):
    try:
        is_authenticated = check_user_authentication(request)
        if not is_authenticated:
            return redirect("login_page")

        handle_unauthorized_instructor(request.user)

        student = StudentProfile.objects.get(user_id=request.user.id)
        course_ids = Enrollment.objects.filter(student=student, status="approved").values_list("course_id", flat=True)
        assignments = Assignment.objects.filter(course_id__in=course_ids).select_related("course")
        marked_submissions = Submission.objects.filter(student=student, status="graded")
        stats = marked_submissions.aggregate(avg_score=Avg("scores__score"), max_score=Max("scores__score"))

        marked_submissions_list = []
        for submission in marked_submissions:
            marked_submissions_list.append({
                "title": submission.assignment.title,
                "score": round(Scores.objects.get(submission=submission).score),
                "course": Course.objects.get(id=submission.assignment.course_id).title,
            })

        return render(request, "student_grades.html", {
            "averageScore": round(stats["avg_score"]) if stats["avg_score"] else 0,
            "assignmentsGraded": marked_submissions.count(),
            "totalAssignments": assignments.count(),
            "highestScore": round(stats["max_score"]) if stats["max_score"] else 0,
            "assignmentList": AssignmentSerializer(assignments, many=True).data,
            "markedSubmissions": marked_submissions_list,
        })
    except StudentProfile.DoesNotExist:
        logger.error(f"[get_student_grades] StudentProfile not found for user {request.user.id}")
        return JsonResponse({"error": "Student profile not found."}, status=404)
    except Exception as e:
        logger.error(f"[get_student_grades] Unexpected error: {e}", exc_info=True)
        return JsonResponse({"error": "Failed to retrieve grades.", "detail": str(e)}, status=500)


@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsStudent])
def get_student_assignments(request):
    try:
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
        pending_assignments = Assignment.objects.filter(course_id__in=course_ids).exclude(submission__student__id=studentId).distinct().count()

        assignments = Assignment.objects.filter(course_id__in=course_ids)
        assignment_list = []

        for assignment in assignments:
            submission = Submission.objects.filter(assignment=assignment, student__id=studentId).first()
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
            "assignmentList": assignment_list,
        })
    except StudentProfile.DoesNotExist:
        logger.error(f"[get_student_assignments] StudentProfile not found for user {request.user.id}")
        return JsonResponse({"error": "Student profile not found."}, status=404)
    except Exception as e:
        logger.error(f"[get_student_assignments] Unexpected error: {e}", exc_info=True)
        return JsonResponse({"error": "Failed to retrieve assignments.", "detail": str(e)}, status=500)


@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructor])
def create_course_material(request, course_id):
    try:
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
                return JsonResponse({"message": "Please provide a title, description, and file."}, status=400)

            blob_name = f"course_{course_id}/{uploaded.name}"
            file_url = upload_file_to_azure(uploaded, blob_name)

            Materials.objects.create(
                course=course,
                uploaded_by=course.instructor,
                title=title,
                description=description,
                file_name=uploaded.name,
                file_url=file_url,
                file_type=uploaded.content_type,
            )

            return JsonResponse({"message": "Lesson published successfully."}, status=201)

        return render(request, "create_lesson.html", {"course_id": course_id})
    except Exception as e:
        logger.error(f"[create_course_material] Unexpected error for course_id={course_id}: {e}", exc_info=True)
        return JsonResponse({"error": "Failed to create course material.", "detail": str(e)}, status=500)


@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructorOrStudent])
def view_course_material(request, material_id):
    try:
        topic = get_object_or_404(Materials, id=material_id)
        topic_material = get_blob_sas_url(topic.file_url, expiry_hours=2) if topic.file_url else None
        serializer = MaterialsSerializer(topic)
        return JsonResponse({"material": serializer.data, "material_url": topic_material}, status=200)
    except Exception as e:
        logger.error(f"[view_course_material] Unexpected error for material_id={material_id}: {e}", exc_info=True)
        return JsonResponse({"error": "Failed to retrieve material.", "detail": str(e)}, status=500)


@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructor])
def modify_course_material(request, material_id):
    try:
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
            return JsonResponse({"message": "Material updated successfully."}, status=200)

        elif request.method == 'DELETE':
            material.delete()
            return JsonResponse({"message": "Material deleted successfully."}, status=200)

        return render(request, "instructor_class.html", {"material_id": material_id, "material": material})
    except Exception as e:
        logger.error(f"[modify_course_material] Unexpected error for material_id={material_id}: {e}", exc_info=True)
        return JsonResponse({"error": "Failed to modify material.", "detail": str(e)}, status=500)


@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructor])
def create_assignment(request, course_id):
    try:
        is_authenticated = check_user_authentication(request)
        if not is_authenticated:
            return redirect("login_page")

        handle_unauthorized_student(request.user)
        course = get_object_or_404(Course, id=course_id)

        if request.method == 'POST':
            try:
                data = json.loads(request.body.decode('utf-8'))
            except json.JSONDecodeError:
                return JsonResponse({"message": "Invalid JSON"}, status=400)

            title = data.get('title')
            description = data.get('description')
            due_date_str = data.get('due_date')

            if not title or not description or not due_date_str:
                return JsonResponse({"message": "Please provide a title, description, and due date."}, status=400)

            due_date = datetime.fromisoformat(due_date_str.replace('Z', '+00:00'))
            if due_date.tzinfo is None:
                due_date = timezone.make_aware(due_date)

            assignment = Assignment.objects.create(
                course_id=course_id,
                title=title,
                description=description,
                due_date=due_date,
            )

            return JsonResponse({"message": "Assignment created successfully.", "assignment_id": assignment.id}, status=201)

        return JsonResponse({"course": CourseSerializer(course).data}, status=200)
    except Exception as e:
        logger.error(f"[create_assignment] Unexpected error for course_id={course_id}: {e}", exc_info=True)
        return JsonResponse({"error": "Failed to create assignment.", "detail": str(e)}, status=500)


@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructor])
def modify_assignment(request, assignment_id):
    try:
        is_authenticated = check_user_authentication(request)
        if not is_authenticated:
            return redirect("login_page")

        handle_unauthorized_student(request.user)
        assignment = get_object_or_404(Assignment, id=assignment_id)

        if request.method == 'PUT':
            try:
                data = json.loads(request.body.decode('utf-8'))
            except json.JSONDecodeError:
                return JsonResponse({"message": "Invalid JSON"}, status=400)

            title = data.get('title')
            description = data.get('description')
            due_date_str = data.get('due_date')

            if title:
                assignment.title = title
            if description:
                assignment.description = description
            if due_date_str:
                due_date = datetime.fromisoformat(due_date_str.replace('Z', '+00:00'))
                if due_date.tzinfo is None:
                    due_date = timezone.make_aware(due_date)
                assignment.due_date = due_date

            assignment.save()
            return JsonResponse({"message": "Assignment updated successfully."}, status=200)

        elif request.method == 'DELETE':
            assignment.delete()
            return JsonResponse({"message": "Assignment deleted successfully."}, status=200)

        return render(request, "instructor_assignments.html", {"assignment_id": assignment_id, "assignment": assignment})
    except Exception as e:
        logger.error(f"[modify_assignment] Unexpected error for assignment_id={assignment_id}: {e}", exc_info=True)
        return JsonResponse({"error": "Failed to modify assignment.", "detail": str(e)}, status=500)


@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructorOrStudent])
def get_assignment_details(request, assignment_id):
    try:
        if request.user.profile.user_type == "student":
            assignment = get_object_or_404(Assignment, id=assignment_id)
            return JsonResponse({"assignment": AssignmentSerializer(assignment).data}, status=200)

        elif request.user.profile.user_type == "instructor":
            assignment = get_object_or_404(Assignment, id=assignment_id)
            submissions = Submission.objects.filter(assignment=assignment).select_related('student__user')
            return JsonResponse({
                "assignment": AssignmentSerializer(assignment).data,
                "submissions": SubmissionSerializer(submissions, many=True).data,
                "due_date": assignment.due_date.isoformat(),
            }, status=200)

        return JsonResponse({"error": "Unknown user type."}, status=400)
    except Exception as e:
        logger.error(f"[get_assignment_details] Unexpected error for assignment_id={assignment_id}: {e}", exc_info=True)
        return JsonResponse({"error": "Failed to retrieve assignment details.", "detail": str(e)}, status=500)


@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsStudent])
def submit_assignment(request, assignment_id):
    try:
        is_authenticated = check_user_authentication(request)
        if not is_authenticated:
            return redirect("login_page")

        handle_unauthorized_instructor(request.user)

        assignment = get_object_or_404(Assignment, id=assignment_id)
        today = timezone.now()

        if today > assignment.due_date:
            return JsonResponse({"message": "Assignment has passed due date."}, status=400)

        student = get_object_or_404(StudentProfile, user=request.user)

        if request.method == 'POST':
            uploaded = request.FILES.get('file')
            if not uploaded:
                return JsonResponse({"message": "Please upload a file."}, status=400)

            blob_name = f"submissions/assignment_{assignment_id}/student_{student.id}/{uploaded.name}"
            file_url = upload_file_to_azure(uploaded, blob_name)

            submission, created = Submission.objects.get_or_create(
                assignment=assignment,
                student=student,
                defaults={"file_url": file_url, "file_name": uploaded.name, "status": "submitted"}
            )
            if not created:
                submission.file_url = file_url
                submission.file_type = uploaded.content_type
                submission.file_name = uploaded.name
                submission.status = "submitted"
                submission.save()

            return JsonResponse({"message": "Assignment submitted successfully."}, status=201)

        return JsonResponse({"assignment": AssignmentSerializer(assignment).data}, status=200)
    except Exception as e:
        logger.error(f"[submit_assignment] Unexpected error for assignment_id={assignment_id}: {e}", exc_info=True)
        return JsonResponse({"error": "Failed to submit assignment.", "detail": str(e)}, status=500)


@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructor])
def get_submissions(request, assignment_id):
    try:
        is_authenticated = check_user_authentication(request)
        if not is_authenticated:
            return redirect("login_page")

        handle_unauthorized_student(request.user)

        assignment = get_object_or_404(Assignment, id=assignment_id)
        submissions = Submission.objects.filter(assignment=assignment.id).select_related('student__user')

        submission_details = []
        for submission in submissions:
            submission_details.append({
                "id": submission.id,
                "assignment": submission.assignment.id,
                "student": StudentProfile.objects.get(id=submission.student.id).user.get_full_name(),
                "file_url": get_blob_sas_url(submission.file_url, expiry_hours=2) if submission.file_url else None,
                "file_name": submission.file_name,
                "status": submission.status,
                "submitted_at": submission.submission_date.strftime("%b %d, %Y - %I:%M %p") if submission.submission_date else None,
            })

        return JsonResponse({"submissions": submission_details}, status=200)
    except Exception as e:
        logger.error(f"[get_submissions] Unexpected error for assignment_id={assignment_id}: {e}", exc_info=True)
        return JsonResponse({"error": "Failed to retrieve submissions.", "detail": str(e)}, status=500)


@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructor])
def get_submission_details(request, submission_id, assignment_id):
    try:
        is_authenticated = check_user_authentication(request)
        if not is_authenticated:
            return redirect("login_page")

        handle_unauthorized_student(request.user)

        submission = get_object_or_404(Submission, id=submission_id, assignment__id=assignment_id)
        return JsonResponse({"submission": SubmissionSerializer(submission).data}, status=200)
    except Exception as e:
        logger.error(f"[get_submission_details] Unexpected error for submission_id={submission_id}: {e}", exc_info=True)
        return JsonResponse({"error": "Failed to retrieve submission details.", "detail": str(e)}, status=500)


@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsInstructor])
def grade_submission(request, submission_id, assignment_id):
    try:
        is_authenticated = check_user_authentication(request)
        if not is_authenticated:
            return redirect("login_page")

        handle_unauthorized_student(request.user)

        if request.method == 'POST':
            try:
                data = json.loads(request.body.decode('utf-8'))
            except json.JSONDecodeError:
                return JsonResponse({"message": "Invalid JSON"}, status=400)

            score = data.get('score')
            feedback = data.get('feedback')

            if not score or not feedback:
                return JsonResponse({"message": "Please provide a score and feedback."}, status=400)

            instructor = InstructorProfile.objects.get(user__id=request.user.id)
            submission = get_object_or_404(Submission, id=submission_id)
            submission.status = "graded"
            submission.save()

            Scores.objects.create(submission=submission, graded_by=instructor, score=score, feedback=feedback)

            return JsonResponse({"message": "Submission graded successfully."}, status=200)

        return JsonResponse({"message": "Invalid request method."}, status=405)
    except InstructorProfile.DoesNotExist:
        logger.error(f"[grade_submission] InstructorProfile not found for user {request.user.id}")
        return JsonResponse({"error": "Instructor profile not found."}, status=404)
    except Exception as e:
        logger.error(f"[grade_submission] Unexpected error for submission_id={submission_id}: {e}", exc_info=True)
        return JsonResponse({"error": "Failed to grade submission.", "detail": str(e)}, status=500)


#################  HELPERS  ###################

def check_user_authentication(request):
    return request.user.is_authenticated


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
    container.upload_blob(name=blob_name, data=file_obj.read(), overwrite=True)
    return f"https://{settings.AZURE_ACCOUNT_NAME}.blob.core.windows.net/{settings.AZURE_CONTAINER}/{blob_name}"


def handle_unauthorized_student(user):
    if user.profile.user_type != "instructor":
        raise PermissionDenied("You do not have permission to access this resource.")


def handle_unauthorized_instructor(user):
    if user.profile.user_type != "student":
        raise PermissionDenied("You do not have permission to access this resource.")