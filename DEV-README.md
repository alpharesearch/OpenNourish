# Developer Notes for OpenNourish

This document contains notes and procedures for developers working on the OpenNourish project.

## Resetting the User Database and Migrations

There are times during development when you may need to completely reset the user database (`user_data.db`) and start fresh. This is useful when the migration history gets corrupted or you want to revert to a clean slate.

**Warning:** This process will permanently delete all data in your `user_data.db` file.

Follow these steps to reset the database and Alembic migration configuration:

1.  **Delete the Database File:**
    Remove the existing SQLite database file.
    ```bash
    rm user_data.db
    ```

2.  **Delete the Migrations Directory:**
    Remove the entire `migrations` directory. This will erase the Alembic history.
    ```bash
    rm -rf migrations
    ```

3.  **Initialize Migrations:**
    Create a new migrations repository.
    ```bash
    flask db init
    ```

4.  **Generate the Initial Migration:**
    Create a new migration script based on the current state of the models in `models.py`.
    ```bash
    flask db migrate -m "Initial migration"
    ```

5.  **Apply the Migration:**
    Apply the newly created migration to the database. This will create all the tables.
    ```bash
    flask db upgrade
    ```

After these steps, you will have a fresh `user_data.db` file and a clean migration history.

## Making Non-Destructive Database Schema Changes

When you need to make changes to the database schema (e.g., adding a new table or column), you should always use a non-destructive workflow to avoid losing data. This is the standard process for evolving the database schema as the application grows.

Follow these steps to make non-destructive schema changes:

1.  **Modify Your Models:**
    Make the desired changes to your models in the `models.py` file. For example, you might add a new column to an existing model or create a new model class.

2.  **Generate a New Migration:**
    Once you have updated your models, generate a new migration script. This script will contain the necessary commands to update the database schema to match your models.
    ```bash
    flask db migrate -m "A short, descriptive message about the changes"
    ```
    Replace "A short, descriptive message about the changes" with a brief summary of your changes (e.g., "Add email column to User model").

3.  **Apply the Migration:**
    Apply the new migration to your database. This will update the database schema without deleting any existing data.
    ```bash
    flask db upgrade
    ```

By following this process, you can safely evolve your database schema as you develop the application, without worrying about losing your data.
