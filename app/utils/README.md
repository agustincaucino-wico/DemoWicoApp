# Email System Documentation

This directory contains a modular email system for sending various types of notifications.

## Structure

```
utils/
├── __init__.py
├── email_utils.py          # Backward compatibility wrapper
├── email_service.py        # Main email service class
├── template_loader.py      # Template loading utility
└── email_templates/        # Email template files
    ├── __init__.py
    ├── invitation_email.html
    ├── invitation_email.txt
    ├── removal_notification.html
    └── removal_notification.txt
```

## Components

### 1. Email Service (`email_service.py`)

The main service class that handles all email operations.

```python
from utils.email_service import email_service

# Send invitation email
success = email_service.send_invitation_email(holder_user, dependent_email, holder_account)

# Send removal notification
success = email_service.send_dependent_removal_notification(holder_user, dependent_user, holder_account)
```

### 2. Template Loader (`template_loader.py`)

Handles loading and rendering email templates.

```python
from utils.template_loader import email_template_loader

html_content, text_content = email_template_loader.load_template('invitation_email', context)
```

### 3. Email Templates (`email_templates/`)

Professional HTML and text templates for different email types:

- **`invitation_email.html/.txt`**: Templates for inviting new dependents
- **`removal_notification.html/.txt`**: Templates for dependent removal notifications

### 4. Email Utils (`email_utils.py`)

Backward compatibility wrapper that maintains the original API.

## Usage Examples

### Basic Usage (Recommended)

```python
from utils.email_service import email_service

# Send invitation
success = email_service.send_invitation_email(
    holder_user=request.user,
    dependent_email="user@example.com",
    holder_account=account
)

# Send removal notification
success = email_service.send_dependent_removal_notification(
    holder_user=request.user,
    dependent_user=dependent_user,
    holder_account=account
)
```

### Legacy Usage (Backward Compatible)

```python
from utils.email_utils import send_invitation_email, send_dependent_removal_notification

# These still work exactly as before
send_invitation_email(holder_user, dependent_email, holder_account)
send_dependent_removal_notification(holder_user, dependent_user, holder_account)
```

### Custom Email Templates

```python
from utils.email_service import email_service

# Send custom email using templates
success = email_service.send_email(
    template_name='custom_template',
    subject='Custom Subject',
    recipient_email='user@example.com',
    context={
        'user_name': 'John Doe',
        'custom_data': 'Some data'
    }
)
```

## Template Variables

### Invitation Email Templates

Available variables:
- `holder_name`: Name of the account holder
- `holder_email`: Email of the account holder
- `account_id`: ID of the holder account
- `dependent_email`: Email of the dependent user
- `app_name`: Application name (from settings)

### Removal Notification Templates

Available variables:
- `holder_name`: Name of the account holder
- `holder_email`: Email of the account holder
- `dependent_name`: Name of the dependent user
- `dependent_email`: Email of the dependent user
- `account_id`: ID of the holder account
- `app_name`: Application name (from settings)

## Configuration

### Django Settings

```python
# Email configuration
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'your-email@gmail.com'
EMAIL_HOST_PASSWORD = 'your-app-password'
DEFAULT_FROM_EMAIL = 'WiCo App <noreply@wico.app>'

# App configuration
APP_NAME = 'WiCo'
```

## Adding New Email Templates

1. **Create template files**:
   ```
   email_templates/
   ├── my_new_template.html
   └── my_new_template.txt
   ```

2. **Use template variables**:
   ```html
   <!-- my_new_template.html -->
   <h1>Hello {user_name}!</h1>
   <p>Your {item_name} is ready.</p>
   ```

3. **Send the email**:
   ```python
   success = email_service.send_email(
       template_name='my_new_template',
       subject='Your item is ready',
       recipient_email=user.email,
       context={
           'user_name': user.name,
           'item_name': 'Order #123'
       }
   )
   ```

## Features

- ✅ **Modular Design**: Separate concerns between service, templates, and utilities
- ✅ **Professional Templates**: Styled HTML emails with fallback text versions
- ✅ **Error Handling**: Comprehensive logging and graceful failure handling
- ✅ **Backward Compatibility**: Existing code continues to work without changes
- ✅ **Extensible**: Easy to add new email types and templates
- ✅ **Template Variables**: Dynamic content insertion with simple formatting
- ✅ **Configuration**: Respects Django settings for email and app configuration

## Error Handling

All email functions return `True`/`False` and log errors without breaking the application flow:

```python
success = email_service.send_invitation_email(holder_user, dependent_email, holder_account)
if not success:
    logger.warning(f"Failed to send invitation email to {dependent_email}")
    # Application continues normally
```

## Migration from Old System

No changes needed! The old import statements continue to work:

```python
# This still works exactly as before
from utils.email_utils import send_invitation_email, send_dependent_removal_notification
```

The functions now use the new modular system internally while maintaining the same API.
