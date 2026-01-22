Neo4j Yelp Graph: Master Load & Modeling Guide
1. Schema Configuration (Constraints)
Run these first. Constraints act as your "Identity Protection" layer, preventing duplicate entities and ensuring the graph scales without data corruption.

Cypher
// Core Entities
CREATE CONSTRAINT FOR (u:User) REQUIRE u.user_id IS UNIQUE;
CREATE CONSTRAINT FOR (b:Business) REQUIRE b.business_id IS UNIQUE;
CREATE CONSTRAINT FOR (r:Review) REQUIRE r.review_id IS UNIQUE;

// Geography & Groupings
CREATE CONSTRAINT FOR (c:Category) REQUIRE c.name IS UNIQUE;
CREATE CONSTRAINT FOR (s:State) REQUIRE s.code IS UNIQUE;
CREATE CONSTRAINT FOR (p:PostalCode) REQUIRE p.code IS UNIQUE;
CREATE CONSTRAINT FOR (ci:City) REQUIRE (ci.name, ci.state) IS UNIQUE;
2. Phase I: The Geographic Skeleton
We load the "Source of Truth" geography first. This ensures that when we load businesses, we link them to verified nodes rather than creating "dirty" duplicates from raw CSV strings.

Cypher
LOAD CSV WITH HEADERS FROM 'file:///business_city.csv' AS row
MERGE (s:State {code: row.state})
MERGE (c:City {name: row.city, state: row.state})
MERGE (c)-[:CLAIMS_STATE]->(s);
3. Phase II: Core Entity Ingestion
We load the primary actors (Users and Businesses) before their interactions (Reviews).

3.1 Load Users
Cypher
LOAD CSV WITH HEADERS FROM 'file:///user_small.csv' AS row
MERGE (u:User {user_id: row.user_id})
SET u.name = row.name,
    u.review_count = toInteger(row.review_count),
    u.yelping_since = row.yelping_since,
    u.useful = toInteger(row.useful),
    u.funny = toInteger(row.funny),
    u.cool = toInteger(row.cool),
    u.fans = toInteger(row.fans),
    u.average_stars = toFloat(row.average_stars);
3.2 Load Businesses & Map Claims
Note that we store the raw city and state as properties on the Business node to preserve the original "Claim," even if it doesn't match our City node yet.

Cypher
LOAD CSV WITH HEADERS FROM 'file:///business_small.csv' AS row
MERGE (b:Business {business_id: row.business_id})
SET b.name = row.name,
    b.raw_city = row.city,
    b.raw_state = row.state,
    b.latitude = toFloat(row.latitude),
    b.longitude = toFloat(row.longitude),
    b.stars = toFloat(row.stars),
    b.is_open = toInteger(row.is_open)

// Link to PostalCode (Discovery Mode: create if it doesn't exist)
MERGE (p:PostalCode {code: row.postal_code})
MERGE (b)-[:CLAIMS_POSTAL_CODE]->(p);
4. Phase III: The Interaction & Social Layer
Now that the "Nouns" (User, Business) exist, we connect them via "Verbs" (Wrote, Of, Friends).

4.1 Reviews
Cypher
LOAD CSV WITH HEADERS FROM 'file:///review_small.csv' AS row
MATCH (u:User {user_id: row.user_id})
MATCH (b:Business {business_id: row.business_id})
MERGE (r:Review {review_id: row.review_id})
SET r.stars = toInteger(row.stars),
    r.date = row.date,
    r.useful = toInteger(row.useful)
MERGE (u)-[:WROTE]->(r)
MERGE (r)-[:OF]->(b);
4.2 Social Friendships
Cypher
LOAD CSV WITH HEADERS FROM 'file:///user_friendship.csv' AS row
MATCH (u1:User {user_id: row.user1})
MATCH (u2:User {user_id: row.user2})
MERGE (u1)-[:FRIENDS_WITH]-(u2);
5. Phase IV: Inference (Derived Relationships)
This is where the graph becomes "intelligent." We link businesses to cities based on their claims and infer user locations.

5.1 Business → City (Heuristic)
Cypher
MATCH (b:Business), (c:City)
WHERE b.raw_city = c.name AND b.raw_state = c.state
MERGE (b)-[:LOCATED_NEAR {confidence: 1.0, method: 'exact_match'}]->(c);
5.2 User → City (Spatial Signal)
Cypher
MATCH (u:User)-[:WROTE]->()-[:OF]->(b:Business)-[:LOCATED_NEAR]->(c:City)
WITH u, c, count(*) AS count
WHERE count >= 3
MERGE (u)-[:LIKELY_RESIDENT_OF {confidence: 0.8, version: 'v1'}]->(c);
6. Verification Queries
Run these to ensure your data is healthy:

Find "Orphan" Businesses (Claims that didn't match a verified city): MATCH (b:Business) WHERE NOT (b)-[:LOCATED_NEAR]->(:City) RETURN b.name, b.raw_city

Check Social Density: MATCH (u:User) RETURN count(u) AS TotalUsers, avg(size((u)-[:FRIENDS_WITH]-())) AS AvgFriends