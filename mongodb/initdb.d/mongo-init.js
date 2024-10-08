// mongosh --username --password --authenticationDatabase admin

function createDatabase(dbName, collectionName, data, indexes) {
    const dbInstance = db.getSiblingDB(dbName);
    if (!dbInstance.getCollectionNames().includes(collectionName)) {
        dbInstance.createCollection(collectionName);
        indexes.forEach(index => {
            dbInstance[collectionName].createIndex(index.fields, index.options);
        });
        dbInstance[collectionName].insertMany(data);
    }
}

createDatabase(
    "github_crawl", 
    "repositories",
    [
        {
            "id": -1,
            "name": "repo_name",
            "full_name": "user/repo_name",
            "private": false,
            "fork": false,
            "url": "https://api.github.com/repos/user/repo_name",
            "html_url": "https://github.com/repos/user/repo_name"
        },
    ],
    [
        { fields: { full_name: 1 }, options: { unique: true } },
    ]
)

createDatabase(
    "stackoverflow_crawl",
    "questions",
    [
        {
            "question_id": -1,
            "title": "question_title",
            "body": "question_body",
            "link": "https://stackoverflow.com/questions/question_id",
            "tags": ["tag1", "tag2"],
            "is_answered": true,
            "view_count": 100,
            "answer_count": 1,
            "score": 1,
            "creation_date": 1615027200,
            "last_activity_date": 1615027200,
        },
    ],
    [
        { fields: { question_id: 1 }, options: { unique: true } }
    ]
)

createDatabase(
    "troubleshooting",
    "search_queries", 
    [
        {
            "user_id": -1,
            "query_text": "query_text",
            "links": ["link1", "link2"],
            "search_engine": "google",
            "created_at": 1615027200,
            "updated_at": 1615027200,
            "conversation": [],
        }
    ],
    [

    ]
)

createDatabase(
    "troubleshooting",
    "reactions",
    [
        {
            "user_id": -1,
            "search_query_id": -1,
            "reaction": "like",
            "created_at": 1615027200,
        }
    ],
    [
        { fields: { user_id: 1, search_query_id: 1 }, options: { unique: true } }
    ]
)

createDatabase(
    "troubleshooting",
    "users",
    [
        {
            "email": "user@example.com",
            "name": "example_name",
            "created_at": 1615027200,
            "updated_at": 1615027200,
            "google_sub": "184248833606034064985",
        }
    ],
    [
        { fields: { email: 1 }, options: { unique: true } },
        { fields: { google_sub: 1 }, options: { unique: true } },
    ]
)
