# OSF based dataset management for research and analyses

### Run Project - POC
# open the project in rstudio
# set up local from project's location
python -m venv venv
source venv/bin/activate

# set up users database
python -m db.init_db
python -m db.seed_users

# run app
shiny run --reload app --port 8500

#deploy
pip install rsconnect-python

#fill in the details from your shinyapps account
rsconnect add --account ACCOUNT --name NAME --token TOKEN --secret SECRET
rsconnect deploy shiny LOCATION_TO_APP_FOLDER --name NAME --title your_app_name


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


## TODOS (Feedback 24/04/2025)

1.  ⁠loader for waiting for columns to appear once dataset has been upload - COMPLETED
2. ⁠deduplication of column names(permno appears 2 times)
3. ⁠⁠unique id is not needed but the selected column (e.g. permno) should be exclusive in train, test, val sets no repeat case.
4. ⁠sholar cannot reupload same dataset once analysis is uploaded - Completed
5. ⁠more guiding/walkthrough help
6. ⁠Analysis has been uploaded information ( to justify validation set download) - Completed
7. ⁠unlock .rda, csv, .xlsx, .dta  for dataset uploads - Completed
8. upload analysis is a word/pdf , render it in the public set - Completed
9. ⁠user can only leave column selection blank for random row spit or user can select one column (see point no 3)
10. Generic info/use on main page


## Dataset Column Handling and Splitting Logic 

Here's a breakdown of how it addresses the "repeated columns" and "unique IDs" concern for column selection:

No More Simple Suffixing for Display: Instead of just showing all columns with suffixes if they had duplicate names (e.g., permno, permno.1, permno.2)

Identifies Original Duplicates: It first figures out which columns in your uploaded file originally had the same name (e.g., two columns were both named "permno").

Selects the "Best" Representative: If there were multiple columns with the same original name, the code now analyzes these versions. It selects the one that has:
More non-missing data.
More unique values (as a tie-breaker).

Shows Only the "Best" or Original Unique Columns: The dropdown list for selecting the "Column for Exclusive Split" will then only show: Columns that had unique names from the start.

The single "best" representative column chosen from any group of originally duplicated columns.
So, if your input file had columnA, columnB, columnA (where the two columnAs might have slightly different data), the process would be:

The system reads them, and pandas might initially name them columnA, columnB, columnA.1.
The new logic in handlers.py identifies that columnA and columnA.1 originated from the same name ("columnA").
It compares columnA and columnA.1 based on data content (non-missing values, unique values).
Let's say columnA is determined to be "better" or more relevant.
The dropdown you see for splitting will then show columnA (the chosen one) and columnB. It will not show columnA.1.
This way, you get a cleaner list of columns to choose from, and for any original duplications, the system tries to pick the most data-rich version to offer for your ID-based split.
preventing clutter from multiple versions of the same original column and guiding towards the most data-rich option for splits.

If you choose "None (Random Split)" or do not select an column, the dataset will be split into train, test, and validation sets randomly based on the specified ratios, without ensuring exclusivity for any particular column's values.

