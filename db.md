
<pre>
```text
+-----------+           +--------------+           +-----------+
|   Users   | 1        *|  Repositories | 1        *|  Datasets  |
+-----------+           +--------------+           +-----------+
| id (PK)   |           | id (PK)       |           | id (PK)   |
| username  |           | user_id (FK)  |           | repository_id (FK) |
| password  |           | repo_name     |           | dataset_type |
| role      |           | is_public     |           | location  |
| created_at|           | created_at    |           | uploaded_at|
+-----------+           +--------------+           +-----------+
      |                          |
      |                          |
      |                          v
      |                  +---------------+
      |                  |  AccessLogs    |
      |                  +---------------+
      |                  | id (PK)        |
      |                  | user_id (FK)   |
      |                  | repository_id (FK) |
      |                  | action         |
      |                  | accessed_at    |
      |                  +---------------+
```
</pre>

