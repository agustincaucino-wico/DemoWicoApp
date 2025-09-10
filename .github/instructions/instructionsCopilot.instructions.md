---
applyTo: '**'
---
Provide project context and coding guidelines that AI should follow when generating code, answering questions, or reviewing changes.


**Frontend**
When using expo-secure-store, import { getItemAsync, setItemAsync } from '../api/apiManager'
The authentication token is called "access_token", and the refresh token is called "refresh_token".
Always try to use the predefined colours instead of new RBG values.
Always use existing components and patterns in the codebase to maintain consistency.
Always use the back/dev/schema.yml when using endpoints

**Backend**
When making views, only implement GET, POST, and DELETE methods unless specified otherwise.
Remember to add the app name into the INSTALLED_APPS setting in settings.py.
Remember to take into account the authentication and permissions for each view.
Always use JWT for authentications, and take in consideration the business logic for the views permissions.
When doing models, add violation_error_message to the constrains of the models.

**Project Structure**: Understand the overall structure of the project, including key directories and files.
**Coding Standards**: Follow established coding standards and best practices for the specific programming languages and frameworks used in the project.
When making new views, ensure that the logic and the UI are separated, and that the UI is responsive and accessible.
**Performance**: Optimize code for performance and scalability, especially in critical areas of the application.