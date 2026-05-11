# 1. Overview
You are asked to design, build, and deploy an **AI-powered analytics dashboard** for a logistics client.
This assignment evaluates your ability to:
* Build a full-stack application
* Work with structured data
* Design meaningful analytics
* Integrate AI responsibly
* Implement forecasting
* Deploy a production-ready system
* Communicate technical decisions clearly

# 2. Project Summary
Build a web application that allows users to explore logistics data through:
* A **traditional analytics dashboard** (KPIs + charts)
* A **natural-language interface powered by AI**

The system should support:
* Querying operational data
* Generating charts dynamically
* Answering business questions
* Predicting demand

# 3. Core Concept
The application must use **one unified dataset** and support three levels of intelligence:

## 3.1 Descriptive Analytics
* Dashboards and visualizations

## 3.2 Diagnostic Analytics
* Natural-language queries answered from data

## 3.3 Predictive & Prescriptive Analytics
* Forecasting demand

# 4. Core Requirements

## 4.1 Dashboard
Create a dashboard for a logistics client.

### Minimum KPIs
* Total orders
* Delivered orders
* Delayed orders
* On-time delivery rate
* Average delivery time

### Minimum Charts (at least 2)
* Order volume over time
* Delivery performance (delayed vs on-time)
* Carrier or destination breakdown

## 4.2 Natural Language Queries
Users must be able to ask questions such as:
* “Show delayed orders by week for the last 3 months”
* “Which carrier has the highest delay rate?”
* “How many orders were delivered late last month?”

The system should:
* Interpret the question
* Retrieve relevant data

Return:
* A direct answer
* A chart
* Or both

## 4.3 Dynamic Chart Generation
The system must:
* Automatically select an appropriate chart type
* Render charts dynamically
* Support a subset of analytical queries

## 4.4 Explainability
For every answer or chart, include:
* Filters used (e.g., time range)
* Metrics and dimensions
* Query plan or structured interpretation (recommended)
* Access to underlying data (table or summary)

## 4.5 Data Handling
* Use the provided dataset or database
* Treat all data as read-only
* Ensure correct aggregation and filtering

# 5. AI-Orchestrated Analytical Tools
The AI layer must act as a **routing and orchestration system**, not as the source of truth.

### Key Principle
AI should:
* Interpret the user’s question
* Select the correct computation path
* Call the appropriate tool
* Present results clearly

**AI must NOT generate answers without computation.**

## 5.1 Required Analytical Tools

### A. Query Tool (Analytics)
Used for:
* Dashboard queries
* Aggregations
* KPI calculations

Examples:
* “Show delayed orders by week”
* “Which carrier has the highest delay rate?”

### B. Forecasting Tool
Used for:
* Predicting future demand

Examples:
* “Predict demand for SKU X for the next 4 months”
* “How much inventory should I plan?”

Requirements:
* Use historical dataset data
* Apply a basic forecasting method

Return:
* Forecast values
* Visualization (historical + forecast)
* Inventory recommendation
* Explanation of methodology

Acceptable methods:
* Moving average
* Linear regression
* Exponential smoothing
* Simple trend models

## 5.2 Expected System Flow
User Question → AI Interpretation → Tool Selection → Structured Input → Computation → Result → Explanation → Visualization

# 6. Deployment Requirements
Your application must:
* Be deployed to a **publicly accessible URL**
* Be fully usable **without local setup**
* Be stable and functional for reviewers

If authentication is used:
* Provide test credentials

Notes:
* You may use any platform (e.g., Vercel, AWS)
* Do NOT commit secrets to the repository

# 8. Technical Expectations
You may use any technology stack.
Examples (optional):
* Frontend: React / Next.js / Vue
* Backend: Node / Python / Java / .NET
* Database: PostgreSQL

# 9. Architecture Guidelines
* Avoid executing raw AI-generated SQL without validation
* Prefer structured query generation
* Clearly separate:
  * AI interpretation
  * Data computation
  * Business logic

# 10. Deliverables
You must submit:
* Source code repository
* Live deployed application URL
* README.md

# 11. README Requirements
Your README must include:
* Setup
  * Local setup instructions
  * Environment variables
* Architecture
  * System overview
  * Key design decisions
  * Data flow
* AI Approach
  * How questions are interpreted
  * How tools are selected
* Assumptions
  * Simplifications made
* Limitations
  * Unsupported features or queries
* Future Improvements
  * What you would build next

# 12. Time Expectation
Expected effort: 6–10 hours

We value:
* Clarity
* Correctness
* Reasoning

Over:
* Completeness
* Polish

# 13. Evaluation Criteria
The following table:

| Category | Weight |
| :--- | :--- |
| Product & UX | 15% |
| Frontend | 15% |
| Backend & Architecture | 20% |
| Data Correctness | 20% |
| AI Orchestration | 15% |
| Forecasting | 10% |
| Deployment | 5% |

# 14. Bonus (Optional)
* Query history
* Caching
* Tests
* Docker setup
* Advanced explainability
* Handling ambiguous queries

# 15. Important Notes
* Do NOT over-engineer
* Prefer simple, correct solutions
* Clearly explain tradeoffs
* Undisclosed AI usage may be treated negatively

# 16. Submission
Provide:
* Repository link
* Deployed app URL
* Credentials (if required)

# 17. What We’re Evaluating
We are evaluating your ability to:
* Build a real product
* Reason about data
* Design intelligent systems
* Use AI responsibly
* Communicate clearly
