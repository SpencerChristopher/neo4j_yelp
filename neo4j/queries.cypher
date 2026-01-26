-- --- Phase 3: Analytical Queries ---

-- 1. Top 10 Businesses by Number of Reviews
-- Identifies businesses that have received the most reviews, indicating popularity or high activity.
-- CORRECTED: Using :REVIEWS relationship and count(r) for clarity.
MATCH (b:Business)<-[:OF]-(r:Review)
WITH b, count(r) AS reviewCount
ORDER BY reviewCount DESC
LIMIT 10
RETURN b.name, b.stars, reviewCount
ORDER BY reviewCount DESC

--

-- 2. Top 10 Users by Number of Reviews
-- Identifies the most active users on the platform.
MATCH (u:User)-[:WROTE]->(r:Review)
WITH u, count(r) AS reviewCount
ORDER BY reviewCount DESC
LIMIT 10
RETURN u.name, u.user_id, reviewCount
ORDER BY reviewCount DESC

--

-- 3. Businesses in a Specific City with High Average Rating
-- Finds businesses within a given city that have an average star rating above a threshold.
-- Uses precise business_id for filtering. Example: Replace 'some_business_id_to_filter' and "San Francisco", 4.5 with desired values.
MATCH (b:Business)
WHERE b.business_id = 'some_business_id_to_filter' -- Example: Filter by ID for robustness
MATCH (b)-[:LOCATED_NEAR]->(c:City)
WHERE c.name = "San Francisco" AND b.stars >= 4.5
RETURN b.name, b.stars, c.name
ORDER BY b.stars DESC

--

-- 4. Social Network Analysis: Users friends with reviewers of a specific business
-- Demonstrates traversing multiple relationships to find social connections related to a business.
-- Uses business_id for precise matching. Example: Replace 'some_business_id_to_filter' with the target business ID.
MATCH (target_business:Business {business_id: 'some_business_id_to_filter'}) -- Using business_id
MATCH (u:User)-[:WROTE]->(:Review)-[:OF]->(target_business)
MATCH (u)-[:FRIENDS_WITH]-(friend:User)
WHERE u <> friend -- Ensure user is not matched with themselves
RETURN DISTINCT u.name AS ReviewerName, friend.name AS FriendName, target_business.name AS BusinessReviewed
ORDER BY ReviewerName, FriendName

--
-- --- NEW ANALYTICAL QUERIES ---

-- 5. Review Cardinality vs. User Residency (Local vs. Out-of-State)
-- Compares review counts for businesses from users inferred as residents vs. non-residents.
-- Helps test the hypothesis of 'lower carenality' for out-of-state reviews.
-- Assumes User has LIKELY_RESIDENT_OF -> City -> State, and Business has LOCATED_IN -> City -> State.
-- This query aims to reveal businesses with a lower proportion of reviews from local users.
-- NOTE: Assumes User.user_id, Business.business_id, Review.review_id, City.name, State.code, and relationship LIKELY_RESIDENT_OF exist and are populated.
MATCH (b:Business)
OPTIONAL MATCH (u:User)-[r:WROTE]->(:Review)-[:OF]->(b)
-- 6. Core Business Categories & User Residency Analysis
-- Analyzes review residency patterns for businesses categorized as "core services".
-- Helps validate the belief that core business reviews should expose user residency patterns.
-- Assumes 'core_categories' list is defined and User has LIKELY_RESIDENT_OF inference.
-- Example core_categories: ['Hair Salons', 'Barbers', 'Restaurants - Basic', 'Pharmacies'] - refine as needed.
-- NOTE: Requires 'Category.name', 'Business.business_id', 'User.user_id', 'Review.review_id', and LIKELY_RESIDENT_OF relationship to be populated.

-- 7. User Residency Inference Analysis
-- Analyzes the distribution of LIKELY_RESIDENT_OF relationships by confidence score, method, and computed timestamp.
-- Helps assess the quality, consistency, and recency of inferred user residency.
-- NOTE: Assumes LIKELY_RESIDENT_OF relationship has properties like 'confidence', 'method', 'computed_at', and potentially lifecycle indicators.


--
-- --- NEW BASIC QUERIES FOR DATA CONFIRMATION ---

-- 8. Node Counts by Label
-- Verifies the number of nodes for each major label in the graph. Essential for confirming successful imports.
CALL db.labels() YIELD label, nodeCount
RETURN label, nodeCount
ORDER BY nodeCount DESC

--

-- 9. Relationship Counts by Type
-- Verifies the number of instances for key relationships. Essential for confirming successful link creation.
CALL db.relationshipTypes() YIELD type, nodeCount
RETURN type, nodeCount
ORDER BY nodeCount DESC
LIMIT 25 -- Show top 25 relationship types

--

-- 10. Sample User with Inferred Residency and Review Summary
-- Shows a sample of users, their inferred residency details, and a summary of their reviews.
-- Helps spot-check data consistency and inference results.
-- NOTE: Requires APOC procedures for map and collection manipulation.


--

-- 11. Check for Duplicate Business IDs (Example for one constraint)
-- Verifies that the 'business_id' unique constraint is effective.
-- If this query returns results, it indicates a problem with constraint enforcement or data loading,
-- as business_id should be unique per Business node.
MATCH (b1:Business), (b2:Business)
WHERE id(b1) < id(b2) AND b1.business_id IS NOT NULL AND b1.business_id = b2.business_id
RETURN b1.business_id, count(b1) AS DuplicateCount
LIMIT 10
-- Repeat for other unique constraints like User.user_id, Review.review_id, etc.

--

-- 12. Check for City and State Identity Constraints
-- Verifies that the composite unique constraints for City and State are effective.
-- City requires (name, state_code) to be unique.
-- State requires (code) to be unique.
MATCH (c1:City), (c2:City)
WHERE id(c1) < id(c2) AND c1.name = c2.name AND c1.state_code = c2.state_code
RETURN c1.name, c1.state_code, count(c1) AS DuplicateCount
LIMIT 10
--
MATCH (s1:State), (s2:State)
WHERE id(s1) < id(s2) AND s1.code IS NOT NULL AND s1.code = s2.code
RETURN s1.code, count(s1) AS DuplicateCount
LIMIT 10

--

-- 13. Check for Postal Code Identity Constraint
-- Verifies that the composite unique constraint for PostalCode (code, country) is effective.
MATCH (p1:PostalCode), (p2:PostalCode)
WHERE id(p1) < id(p2) AND p1.code IS NOT NULL AND p1.code = p2.code
RETURN p1.code, count(p1) AS DuplicateCount
LIMIT 10
