# accounts/views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.contrib.auth import get_user_model, authenticate
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.urls import reverse
from django.http import HttpResponseRedirect

from .serializers import UserSerializer

User = get_user_model()


@api_view(['POST'])
@permission_classes([AllowAny])
def register(request):
    """
    API Endpoint: POST /api/register/
    Registers a new user.
    - If verified user exists with same email → reject
    - If unverified user exists → delete and replace
    - Otherwise → create new user
    Expects: first_name, last_name, email, username, city, state, password
    """
    email = request.data.get('email')

    # Check if user already exists
    existing_user = User.objects.filter(email=email).first()
    if existing_user:
        if existing_user.is_verified:
            return Response({
                "error": "This email is already registered and verified."
            }, status=status.HTTP_400_BAD_REQUEST)
        else:
            # 🚀 Delete old unverified account so user can register fresh
            existing_user.delete()

    # Proceed with registration
    serializer = UserSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save(is_verified=False)

        # Generate verification token
        token = user.generate_verification_token()
        verify_url = request.build_absolute_uri(
            reverse('verify-email', args=[token])
        )

        # Render email
        html_content = render_to_string('emails/verify_email.html', {
            'user': user,
            'verify_url': verify_url,
            'frontend_url': settings.FRONTEND_URL,
        })
        text_content = strip_tags(html_content)

        try:
            msg = EmailMultiAlternatives(
                subject="Confirm Your Email Address",
                body=text_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[user.email],
            )
            msg.attach_alternative(html_content, "text/html")
            msg.send()
        except Exception as e:
            user.delete()  # Avoid orphaned account
            return Response({
                "error": "Failed to send verification email. Please try again."
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            "message": "Registration successful. Please check your email to verify your account."
        }, status=status.HTTP_201_CREATED)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
def login(request):
    """
    API Endpoint: POST /api/login/
    Authenticates user by email and password.
    Returns: token, user info (id, email, name, is_verified), and profile status.
    Blocks login if email is not verified.
    """
    email = request.data.get('email')
    password = request.data.get('password')

    if not email or not password:
        return Response({
            "error": "Email and password are required."
        }, status=status.HTTP_400_BAD_REQUEST)

    # Authenticate user
    user = authenticate(email=email, password=password)
    if not user:
        return Response({
            "error": "Invalid credentials."
        }, status=status.HTTP_401_UNAUTHORIZED)

    # Check email verification
    if not user.is_verified:
        return Response({
            "error": "Email not verified. Please check your inbox for the verification link."
        }, status=status.HTTP_403_FORBIDDEN)

    # ✅ SAFE: Import Token only when needed (after auth passes)
    from rest_framework.authtoken.models import Token

    # Delete old tokens (optional) and create new one
    Token.objects.filter(user=user).delete()
    token, created = Token.objects.get_or_create(user=user)

    return Response({
        "token": token.key,
        "user": {
            "id": user.id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "username": user.username,
            "city": user.city,
            "state": user.state,
            "is_verified": user.is_verified,
            "date_joined": user.date_joined,
        }
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def profile(request):
    """
    API Endpoint: GET /api/profile/
    Returns authenticated user's full profile.
    Requires token in Authorization header.
    """
    user = request.user
    return Response({
        "id": user.id,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "username": user.username,
        "city": user.city,
        "state": user.state,
        "is_verified": user.is_verified,
        "date_joined": user.date_joined,
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def verify_email(request, token):
    """
    API Endpoint: GET /api/verify-email/<token>/
    Verifies user's email using token.
    Redirects to frontend at /verify-email with ?status=success or ?status=invalid.
    """
    try:
        user = User.objects.get(verification_token=token)
        user.is_verified = True
        user.verification_token = None
        user.save(update_fields=['is_verified', 'verification_token'])

        # ✅ Redirect to dedicated verification result page
        redirect_url = f"{settings.FRONTEND_URL}/verify-email?status=success"
        return HttpResponseRedirect(redirect_url)

    except User.DoesNotExist:
        # 🔁 Invalid or expired token
        redirect_url = f"{settings.FRONTEND_URL}/verify-email?status=invalid"
        return HttpResponseRedirect(redirect_url)


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_user_phone(request):
    phone = request.data.get('phone')
    if not phone:
        return Response({"error": "Phone number is required"}, status=status.HTTP_400_BAD_REQUEST)
    
    # Basic validation: must start with +234 and be 13–14 digits
    if not phone.startswith('+234') or not phone[4:].isdigit() or len(phone) < 13 or len(phone) > 14:
        return Response({"error": "Please enter a valid Nigerian phone number (e.g., +2348012345678)"}, status=status.HTTP_400_BAD_REQUEST)

    request.user.phone = phone
    request.user.save(update_fields=['phone'])
    return Response({"message": "Phone number saved successfully"}, status=status.HTTP_200_OK)