# OSF based dataset management for research and analyses

### Run Project - POC

#### Imp Note : Delete poc.db before running the latest dev code

1. python -m db.init_db
2. python -m db.seed_users
3. shiny run --reload app --port 8500 


## Requirement

### From research team
We are writing a paper on a very very simple idea: cross-validation. We ask management scholars to do cross-validation–no one does it. to support the paper, we want to create a repository, something similar to pre-registration like aspredicted.org https://researchbox.org/ or https://osf.io/ The scholars should upload their data, the repo automatically splits the data into three: training, test and validation sets. keeps the last one, and return the scholar the training and test sets. the scholar can do all the analyses, upload the results and then is allowed to dowload the validation set. because storage is costly, our ideal scenario is to have something that can be integrated to researchbox.org or osf.io However, for this submission, we just need a minimum viable product to impress the reviewers

### Restructured Requirement for POC
For POC we can just have two types of users in the tool i.e. scholar and peer, scholar uploads a dataset, the tool splits the dataset into train, validation and test sets and creates a repo for the scholar.  The tool allows the scholar to download the train and test set from the repo, the scholar can then, upload all the analyses and results.

On uploading the analyses and results, the scholar is allowed to download the validation set from the repo.

Now scholar is also presented an option to make the repo public, this allows any peer user to download the datasets as well, else only scholar has access.

#### User stories
1. By default, any user takes the role of peer and can see the Public datasets.
2. On clicking any dataset (link), a pop up shows the file structure inside.
3. peer can click download on the pop up to download the train and test sets
4. Any user has an option to sign-in (hard coded for POC, else using OSF), to access their scholar profile
5. scholar profile has a list of the repos uploaded by them
6. on clicking any repo , they can see the internal file structure, with available download and upload options
7. scholar can create a new repo, which lets them upload a raw dataset
8. upon upload, train, test and validation sets are created by backend and scholar can download train. test sets only
9. they can upload analyses based on the train and test sets
10. for repos with uploaded analyses , scholar can download all 3 i.e. train, test and validation set
11. scholar can make their repo public, which will show up in the list of repos any peer can see.

### Technical Implementation
1. System Architecture
 - Client Layer:
    - Web(only) Interface: Handles user interactions and data presentation
    - Authentication Service: Manages user authentication and role-based access control

2. Core Services Layer:

- Dataset Service: Manages dataset operations including splitting into train/validation/test sets
- Repo Service: Controls repository creation and access permissions

3. Storage Layer:

- Database: Stores user information and repositories
- File System: Maintains the actual datasets and analysis files


