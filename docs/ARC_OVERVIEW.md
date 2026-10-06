# AI Teacher Platform - Architecture Overview

**Document:** `ARCH_OVERVIEW.md`  
**Purpose:** Overall architecture for a real-time AI teaching platform that teaches course material, presents visual lessons, answers student questions, uses an authorized per-teacher cloned voice, tracks students, and scales toward hundreds of simultaneous AI classes.

---

## 1. Vision

The platform provides a live AI classroom in which an AI teacher can:

- Teach from uploaded PDF, PPTX, DOCX, Markdown, and other course material.
- Present slides and dynamic visual explanations in real time.
- Speak with an individual teacher's authorized cloned voice using OmniVoice.
- Listen to student questions and support interruption while teaching.
- Pause the lesson, answer a question using course knowledge, and resume from the previous point.
- Adapt explanations to the student's knowledge and progress.
- Conduct quizzes and learning checks.
- Manage registration, attendance, progress, completion, and course statistics.
- Scale horizontally toward approximately 500 or more simultaneous AI classes.

The product should treat the base LLM, TTS engine, vector search engine, and media provider as replaceable infrastructure. The main product logic lives in the **Teacher Orchestrator, Lesson Engine, Student Model, and classroom experience**.

---

## 2. High-Level Architecture

```text
                                 STUDENT
                                    |
                                    v
                      +---------------------------+
                      |      WEB CLASSROOM        |
                      | React + TypeScript        |
                      |                           |
                      | - Teaching Canvas         |
                      | - Teacher Audio           |
                      | - Student Microphone      |
                      | - Slides / Diagrams       |
                      | - Questions / Quiz        |
                      +-------------+-------------+
                                    |
                   +----------------+----------------+
                   |                |                |
                 HTTPS          WebSocket          WebRTC
                   |                |                |
                   v                v                v
             +------------------------------------------------+
             |             EDGE / API / REALTIME LAYER         |
             | CDN / Front Door / Load Balancer / API Gateway  |
             +-------------------------+------------------------+
                                       |
                                       v
                           +------------------------+
                           |    SESSION MANAGER     |
                           | class / teacher /      |
                           | student / lesson state |
                           +-----------+------------+
                                       |
                                       v
                           +------------------------+
                           | TEACHER ORCHESTRATOR   |
                           |      CORE BRAIN        |
                           +-----------+------------+
                                       |
            +--------------------------+--------------------------+
            |                          |                          |
            v                          v                          v
    +---------------+          +---------------+          +---------------+
    | Lesson Engine |          | Student Model |          | Knowledge/RAG |
    +-------+-------+          +-------+-------+          +-------+-------+
            |                          |                          |
            +--------------------------+--------------------------+
                                       |
                                       v
                               +---------------+
                               |  LLM ROUTER   |
                               +-------+-------+
                                       |
                         generated teaching content
                                       |
                     +-----------------+-----------------+
                     |                                   |
                     v                                   v
             +---------------+                   +---------------+
             | Voice Service |                   | Presentation  |
             | + OmniVoice   |                   | Service       |
             +-------+-------+                   +-------+-------+
                     |                                   |
               audio stream                        visual events
                     |                                   |
                     +-----------------+-----------------+
                                       |
                                       v
                                WEB CLASSROOM
```

---

## 3. Frontend: Web Classroom

The web application is the student's live classroom. It should focus on interaction and rendering rather than heavy AI computation.

### Recommended stack

- React
- TypeScript
- Tailwind CSS
- WebRTC for low-latency media/audio paths
- WebSocket for bidirectional classroom events and control commands
- HTTPS/REST for normal APIs
- Canvas/SVG/WebGL as needed for dynamic teaching visuals

### Responsibilities

- Authenticate the student.
- Join or start a classroom session.
- Capture student microphone audio.
- Play streamed teacher audio.
- Render slides and the teaching canvas.
- Render diagrams, equations, code, images, animations, and quizzes.
- Send interaction events such as pause, question, answer, and raise-hand.
- Receive semantic presentation commands from the backend.
- Display connection/teacher/listening states.

### Communication split

```text
Browser
   |
   +---- HTTPS ------> Authentication, course APIs, registration
   |
   +---- WebSocket --> Slide/action/state/quiz/control events
   |
   +---- WebRTC -----> Realtime microphone/audio media path
```

---

## 4. API Gateway and Authentication

The API Gateway is the public entry point for non-media backend operations.

### Responsibilities

- Authentication and authorization.
- JWT/session token validation.
- Rate limiting.
- Request routing.
- Course and teacher APIs.
- Student registration APIs.
- Classroom session creation.
- Issue short-lived credentials needed for realtime connections.

### Example API surface

```text
POST /api/auth/login

POST /api/courses
POST /api/courses/{id}/materials
GET  /api/courses/{id}

GET  /api/teachers
GET  /api/teachers/{id}

POST /api/courses/{id}/register
GET  /api/courses/{id}/statistics

POST /api/classes/start
POST /api/classes/{id}/end
GET  /api/classes/{id}

GET  /api/students/{id}/progress
```

---

## 5. Session Manager

The Session Manager tracks the live state of every classroom. It is essential for interruption, failover, and lesson resume.

### Example state

```json
{
  "class_id": "class_48372",
  "course_id": "gpt101",
  "teacher_id": "teacher_nguyen",
  "current_slide": 17,
  "topic": "self_attention",
  "subtopic": "query_vector",
  "state": "ANSWERING_QUESTION",
  "resume_point": {
    "slide": 17,
    "section": "query_key_similarity"
  }
}
```

### Recommended storage

Use Redis for hot/realtime state such as:

- Active classroom state.
- Current slide and concept.
- Current speaker/listening status.
- Interruption state.
- Short conversation context.
- Resume point.
- Distributed locks and ephemeral coordination.

Persist meaningful long-term events separately in PostgreSQL.

---

## 6. Teacher Orchestrator

The **Teacher Orchestrator is the central application service and the core product logic**.

It does not simply ask an LLM for an answer. It decides what the teacher should do next based on:

- Lesson plan.
- Current teaching position.
- Student question.
- Retrieved course knowledge.
- Student mastery/profile.
- Classroom state.
- Presentation state.
- Voice state.

### Example state machine

```text
+------+     start     +----------+
| IDLE | ------------> | TEACHING |
+------+               +----+-----+
                           |
                     interruption
                           |
                           v
                       +-------+
                       | PAUSE |
                       +---+---+
                           |
                           v
                     +-----------+
                     | LISTENING |
                     +-----+-----+
                           |
                           v
                     +-----------+
                     | ANSWERING |
                     +-----+-----+
                           |
                           v
                    +------------+
                    | CONFIRMING |
                    +-----+------+
                          |
                     understood
                          |
                          +-----------> TEACHING
```

### Typical actions

```text
speak(text)
stop_speaking()
pause_lesson()
resume_lesson()
answer_question(question)
retrieve_course_context(query)
goto_slide(slide_id)
highlight(target)
show_diagram(diagram_id)
start_quiz(quiz_id)
record_understanding(concept, level)
complete_lesson()
```

The orchestrator should produce structured actions where possible and keep free-form LLM output away from direct infrastructure control.

---

## 7. Lesson Engine

The Lesson Engine defines **what should be taught and in what order**.

A lesson should preferably be prepared before live teaching rather than forcing the LLM to invent the entire class continuously.

### Example lesson plan

```json
{
  "lesson": "Self Attention",
  "sections": [
    {
      "concept": "embedding",
      "slide": 1,
      "target_duration_sec": 120
    },
    {
      "concept": "query_key_value",
      "slide": 5,
      "target_duration_sec": 300
    },
    {
      "concept": "attention_score",
      "slide": 9,
      "target_duration_sec": 300
    },
    {
      "type": "quiz",
      "slide": 14
    }
  ]
}
```

### Separation of responsibility

```text
Lesson Engine  -> WHAT to teach
Teacher Agent  -> HOW to teach/explain
Student Model  -> HOW MUCH detail/difficulty is appropriate
RAG            -> WHAT course evidence should ground the explanation
```

---

## 8. Knowledge / RAG Service

Course documents should normally be handled using Retrieval-Augmented Generation instead of retraining a base LLM whenever documents change.

### Ingestion pipeline

```text
PDF / PPTX / DOCX / Markdown / Text
                 |
                 v
           Document Parser
                 |
                 v
              Clean
                 |
                 v
              Chunk
                 |
                 v
      Metadata + Embeddings
                 |
                 v
         Vector/Search Index
```

Useful metadata includes:

```text
course_id
chapter_id
lesson_id
section
slide_number
page_number
document_id
content_type
access_scope
```

### Query path

```text
Student Question
       |
       v
Teacher Orchestrator
       |
       v
Knowledge Service
       |
       v
Hybrid / semantic / vector retrieval
       |
       v
Relevant course chunks
       |
       v
LLM
       |
       v
Grounded teaching answer
```

The service should return both retrieved content and citation metadata so the UI can optionally show the source slide/page.

---

## 9. LLM Router

Do not use the most expensive or largest model for every decision.

```text
                       LLM Router
                           |
          +----------------+----------------+
          |                |                |
          v                v                v
      Fast/Small        Teaching         Reasoning
       Model             Model             Model
```

### Routing examples

- "Yes" / "No" / simple classroom state: deterministic logic or a small model.
- Normal explanation of a course concept: teacher model.
- Difficult derivation or deep reasoning question: stronger reasoning model.
- Slide transition: deterministic application logic whenever possible.

This routing becomes important for cost and capacity when hundreds of classes are active.

---

## 10. Voice Service and OmniVoice

Voice must be separate from the LLM. The LLM is the reasoning/teaching brain; OmniVoice is the teacher's vocal identity.

### Teacher profile example

```json
{
  "teacher_id": "teacher_nguyen",
  "voice_profile_id": "voice_nguyen_01",
  "language": "en",
  "style": "friendly_beginner",
  "speaking_speed": 0.92
}
```

### Pipeline

```text
Teacher Orchestrator
        |
        | streaming text/phrases
        v
    Voice Service
        |
        +--> Voice profile lookup
        +--> Text chunking
        +--> Pronunciation/style controls
        +--> TTS scheduling
        |
        v
    OmniVoice GPU Pool
        |
        v
   Streaming Audio
        |
        v
      Student
```

### Scaling principle

Never dedicate one GPU permanently to one teacher. Use a scheduler and a pool of GPU workers capable of servicing multiple TTS streams.

```text
500 class sessions
       |
       v
  Voice Scheduler
       |
 +-----+-----+-----+
 |           |     |
 v           v     v
GPU #1     GPU #2 ... GPU #N
```

The number and type of GPUs must be defined by benchmark results for the selected OmniVoice model, hardware, language mix, chunk size, batching strategy, and latency SLO.

### Voice authorization

For voices based on real people, store explicit authorization/consent and lifecycle metadata with each voice profile. Voice enrollment, access, deletion, and audit should be controlled operations.

---

## 11. Presentation Service

The runtime classroom should ideally use a dynamic web teaching canvas. PowerPoint can remain an input/export format, but it should not impose limitations on the live AI experience.

The backend should send **semantic presentation events**, not raw HTML generated by the LLM.

### Examples

```json
{
  "type": "presentation.action",
  "action": "goto_slide",
  "slide": 17
}
```

```json
{
  "type": "presentation.action",
  "action": "highlight",
  "target": "query_vector"
}
```

```json
{
  "type": "presentation.action",
  "action": "show_diagram",
  "diagram_id": "qkv_flow"
}
```

### Supported actions can grow to include

- `goto_slide`
- `next_slide`
- `previous_slide`
- `highlight`
- `show_diagram`
- `show_equation`
- `show_code`
- `show_image`
- `start_animation`
- `start_quiz`
- `pause`
- `resume`

---

## 12. Student Model

The Student Model allows the teacher to adapt to each learner instead of behaving like a static narrator.

### Example mastery state

```json
{
  "student_id": "student_1001",
  "mastery": {
    "python": 0.9,
    "linear_algebra": 0.7,
    "probability": 0.5,
    "neural_networks": 0.7,
    "attention": 0.3
  }
}
```

### Uses

- Select explanation difficulty.
- Identify missing prerequisites.
- Choose examples.
- Decide whether to repeat a concept.
- Generate targeted quizzes.
- Track misconceptions.
- Recommend revision material.

Only meaningful learning events should become persistent records.

---

## 13. Registration, Attendance, and Course Completion

Administrative counts should come from deterministic database queries, **not from LLM memory**.

### Class Management Service

```text
Course
  |
  v
Registration
  |
  +--> Attendance
  |
  +--> Progress
  |
  +--> Quiz Results
  |
  +--> Completion
  |
  +--> Pass/Fail
  v
PostgreSQL
```

### Statistics example

```json
{
  "course_id": "AI101",
  "registered": 30,
  "attended": 28,
  "completed": 25,
  "passed": 23
}
```

At the end of a class/course, the Teacher Orchestrator may call a controlled tool such as:

```text
get_course_statistics(course_id)
```

and then present the result naturally.

### Possible completion workflow

```text
Course completed
      |
      v
Check requirements
      |
      +--> Attendance >= configured threshold
      +--> Required lessons completed
      +--> Quiz/exam >= configured pass score
      |
      v
    PASS
      |
      v
Certificate / completion record
      |
      v
Notify student
```

---

## 14. Data Architecture

Use storage according to data lifetime and access pattern.

```text
                          DATA LAYER
                              |
      +-----------------------+-----------------------+
      |                       |                       |
      v                       v                       v
 PostgreSQL                 Redis            Vector/Search Index
 permanent data          realtime state         course knowledge
      |
      +-----------------------+
                              |
                              v
                       Object Storage
                    files / media / assets
```

### PostgreSQL

Store durable structured data:

```text
users
teachers
teacher_voice_profiles
voice_authorizations
students
courses
course_registrations
lessons
classes
attendance
questions
quizzes
quiz_results
student_progress
concept_mastery
completion_records
```

### Redis

Store transient state:

```text
active sessions
current slide
current lesson position
speaker state
recent conversation context
interruption state
resume point
short-lived caches
locks
```

### Vector/Search index

Store:

```text
course chunks
embeddings
metadata
source/citation information
```

### Object storage

Store:

```text
PDFs
PPTX files
DOCX files
images
video
lesson assets
generated slide assets
authorized voice reference material
```

---

## 15. Event and Messaging Layer

Use an asynchronous message bus for work that does not belong in the realtime audio hot path.

Possible implementation:

- Azure Service Bus
- Kafka
- RabbitMQ

### Good event-bus candidates

```text
course.uploaded
document.index.requested
document.index.completed
student.registered
class.started
class.completed
quiz.completed
concept.mastery.updated
certificate.requested
analytics.event
```

Avoid routing each audio chunk through the general event bus.

---

## 16. Realtime Student Interruption Flow

A core user experience is allowing a student to interrupt naturally.

```text
Teacher is speaking
       |
       v
Student begins speaking
       |
       v
Frontend / realtime layer detects interruption
       |
       +--> Stop/duck teacher audio
       |
       +--> Notify Teacher Orchestrator
       |
       v
Save lesson resume position
       |
       v
LISTENING
       |
       v
Speech understanding / transcript
       |
       v
Question identified
       |
       +--> Retrieve course context with RAG
       +--> Read student mastery/context
       +--> Generate answer with LLM
       +--> Select supporting visual
       |
       v
OmniVoice streams answer
       |
       v
Teacher asks for understanding check
       |
       +--> Not understood -> explain differently
       |
       +--> Understood
                    |
                    v
              Restore context
                    |
                    v
               Resume lesson
```

The session must retain enough state to resume correctly even if the interruption lasts several minutes.

---

## 17. Example End-to-End Teaching Sequence

```text
1. Student opens the Web Classroom.
2. Student authenticates and joins a registered course/class.
3. Backend loads student, course, teacher, lesson, and voice profile.
4. Session Manager creates/loads realtime state.
5. Lesson Engine supplies the current teaching step.
6. Teacher Orchestrator requests grounded context when needed.
7. LLM Router selects the appropriate model.
8. Teacher Orchestrator produces speech content + presentation actions.
9. Voice Service streams content through OmniVoice.
10. Presentation Service sends slide/visual events through WebSocket.
11. Browser plays audio and renders visual actions.
12. Student interrupts through the microphone.
13. Orchestrator pauses, saves the resume point, answers, checks understanding.
14. Orchestrator resumes the lesson.
15. Quiz/learning events update the Student Model.
16. Meaningful progress is written to PostgreSQL.
17. At course end, Class Management calculates registration, attendance,
    completion, pass/fail, and optional certificate eligibility.
```

---

## 18. Scaling Toward 500 Simultaneous AI Classes

For 500 simultaneous classes, the main capacity concerns are expected to be LLM throughput/quota, realtime media, and TTS GPU concurrency rather than basic REST APIs.

### Production shape

```text
                         Internet
                            |
                    CDN / Front Door
                            |
                     Load Balancer
                       /         \
                      /           \
             Realtime Media      API Gateway
                      \           /
                       \         /
                        v       v
                      Kubernetes / AKS
                            |
          +-----------------+------------------+
          |                 |                  |
          v                 v                  v
  Teacher Service xN   Knowledge xN      Voice Service xN
          |                 |                  |
          v                 v                  v
       LLM APIs        AI Search          GPU Worker Pool
          |
          +------------------+------------------+
                             |
                    Redis + PostgreSQL
```

### Scaling rules

- Keep application services stateless where practical.
- Store recoverable live state in Redis.
- Autoscale API/orchestrator services horizontally.
- Scale Voice Service independently from RAG and API services.
- Benchmark OmniVoice concurrency before defining GPU counts.
- Use CDN/object storage for static slides/images/media.
- Avoid sending large static assets through FastAPI.
- Avoid synchronous long-running document ingestion inside API workers.
- Use load tests at 10, 50, 100, 250, then 500 simultaneous classes.

### Suggested service-level indicators

Measure at least:

```text
teacher response time: p50 / p95 / p99
LLM time to first token
TTS time to first audio
RAG query latency
audio buffer underruns
WebRTC connection failures
WebSocket event latency
active classes
active teacher speech streams
GPU utilization
GPU queue time
Redis latency
DB connection saturation
session recovery rate
cost per AI teaching hour
```

Do not finalize infrastructure sizing until these measurements are available from a representative workload.

---

## 19. Deployment Evolution

Do not begin with maximum infrastructure complexity.

### Phase 1: MVP

```text
React Web App
      |
WebRTC / WebSocket
      |
FastAPI Backend
      |
 +----+------+---------+
 |           |         |
Teacher     RAG      Voice
Engine               Service
 |                     |
LLM                 OmniVoice

Redis + PostgreSQL + Object Storage
```

Goals:

1. Teach uploaded material.
2. Present slides/canvas.
3. Speak using an authorized custom teacher voice.
4. Student can interrupt.
5. AI answers using course knowledge.
6. Lesson resumes correctly.
7. Registration and progress are recorded.

### Phase 2: 10-50 concurrent classes

Separate expensive workers:

```text
FastAPI / Orchestrator
          |
    +-----+------+
    |            |
 AI Workers   Voice Workers
    |            |
   LLM        OmniVoice GPU
```

Add robust Redis session management, queues for background jobs, metrics, and tracing.

### Phase 3: 100-500 concurrent classes

```text
API Gateway
     |
Kubernetes / AKS
     |
 +---+-------------+----------------+
 |                 |                |
Teacher xN     Knowledge xN     Voice xN
 |                 |                |
LLM             Search          GPU Pool

Redis Cluster / managed Redis
PostgreSQL managed service
Object Storage + CDN
Message Bus
Central telemetry
```

Scale each bottleneck independently.

---

## 20. Suggested Repository Structure for V1

Start as a modular monolith so service boundaries are clear without premature microservice overhead.

```text
ai-teacher/

├── frontend/
│   ├── src/
│   │   ├── classroom/
│   │   ├── presentation/
│   │   ├── audio/
│   │   ├── quiz/
│   │   └── api/
│   └── ...
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── auth/
│   │   ├── teacher/
│   │   │   ├── orchestrator/
│   │   │   └── state_machine/
│   │   ├── lesson/
│   │   ├── session/
│   │   ├── knowledge/
│   │   ├── llm/
│   │   ├── voice/
│   │   ├── presentation/
│   │   ├── student/
│   │   ├── class_management/
│   │   ├── persistence/
│   │   └── common/
│   └── tests/
│
├── workers/
│   ├── document_ingestion/
│   └── voice/
│
├── infra/
│   ├── docker/
│   ├── terraform-or-bicep/
│   └── kubernetes/
│
└── ARCH_OVERVIEW.md
```

Later, extract individual modules into services only when scaling, ownership, deployment frequency, or reliability requirements justify it.

---

## 21. Recommended Technology Stack

```text
Frontend
  React
  TypeScript
  Tailwind CSS
  WebRTC
  WebSocket

Backend
  Python
  FastAPI
  asyncio
  Pydantic

Teacher Intelligence
  Teacher Orchestrator
  Explicit state machine
  Lesson Engine
  Student Model
  LLM Router

Knowledge
  Azure AI Search or equivalent hybrid/vector search
  Embedding model

Voice
  OmniVoice
  GPU worker pool
  Voice Scheduler

Realtime State
  Redis

Persistent Data
  PostgreSQL

Files and Assets
  Azure Blob Storage or equivalent object storage
  CDN

Async Work
  Azure Service Bus / Kafka / RabbitMQ

Deployment
  Docker
  Azure Kubernetes Service when scale requires it

Observability
  OpenTelemetry
  Application Insights and/or Prometheus/Grafana
```

---

## 22. Security and Safety Boundaries

At minimum:

- Authenticate users and authorize access by course/class.
- Do not expose LLM/TTS/search provider keys to the browser.
- Use short-lived realtime credentials where applicable.
- Isolate one class/session from another.
- Apply document-level access control in retrieval.
- Validate all tool/action arguments produced by AI before execution.
- Rate-limit expensive AI operations.
- Encrypt sensitive data and voice reference material.
- Require explicit authorization for cloned real-person voices.
- Provide deletion/revocation for stored voice profiles.
- Record important administrative/audit operations.
- Do not let the LLM become the source of truth for grades, attendance, registration, payment, or completion.

---

## 23. Design Principles

### 1. The LLM is not the whole teacher

```text
LLM             = language/reasoning engine
RAG             = textbook/grounding
Lesson Engine   = teaching roadmap
Student Model   = learner understanding
Orchestrator    = teaching behavior/control
OmniVoice       = authorized vocal identity
Presentation    = visual communication
Database        = authoritative records
```

### 2. Keep realtime audio separate from normal API traffic

Use the media path for media and the application path for commands/state.

### 3. Prefer deterministic tools for deterministic data

Registration count, scores, attendance, completion, slide numbers, and permissions come from services/databases, not model guesses.

### 4. Keep infrastructure replaceable

Hide LLM, search, TTS, storage, and media providers behind internal interfaces.

### 5. Optimize for cost per teaching hour

At large scale, monitor the cost of:

```text
LLM
+ speech understanding
+ OmniVoice/TTS inference
+ retrieval
+ media transport
+ application infrastructure
= total cost per AI teaching hour
```

### 6. Build V1 as a modular monolith

Prove the classroom experience first. Split into microservices when measured bottlenecks demand it.

---

## 24. Final Architecture Summary

```text
                              STUDENT
                                 |
                                 v
                    +-------------------------+
                    |     WEB CLASSROOM       |
                    | React / TypeScript      |
                    +------------+------------+
                                 |
                   HTTPS + WebSocket + WebRTC
                                 |
                                 v
                    +-------------------------+
                    | API / REALTIME EDGE     |
                    +------------+------------+
                                 |
                                 v
                    +-------------------------+
                    |  SESSION MANAGER        |
                    +------------+------------+
                                 |
                                 v
                    +-------------------------+
                    | TEACHER ORCHESTRATOR    |
                    |      CORE PRODUCT       |
                    +------------+------------+
                                 |
            +--------------------+--------------------+
            |                    |                    |
            v                    v                    v
    +---------------+    +---------------+    +---------------+
    | Lesson Engine |    | Student Model |    | Knowledge/RAG |
    +-------+-------+    +-------+-------+    +-------+-------+
            |                    |                    |
            +--------------------+--------------------+
                                 |
                                 v
                         +---------------+
                         |  LLM Router   |
                         +-------+-------+
                                 |
                   +-------------+-------------+
                   |                           |
                   v                           v
             +-----------+               +-----------+
             | Voice     |               | Visual /  |
             | Service   |               | Present   |
             +-----+-----+               +-----+-----+
                   |                           |
              OmniVoice                    events
              GPU Pool                        |
                   |                           |
                   +-------------+-------------+
                                 |
                                 v
                         WEB CLASSROOM

Supporting platform services:

PostgreSQL    -> authoritative persistent records
Redis         -> live classroom/session state
AI Search     -> course knowledge and retrieval
Blob/CDN      -> documents and teaching assets
Message Bus   -> asynchronous business/background events
Observability -> logs, traces, metrics, cost and SLO monitoring
```

The architecture is intentionally designed so the **Teacher Orchestrator + Lesson Engine + Student Model** remain the durable center of the product while LLMs, OmniVoice, search services, and hosting infrastructure can evolve independently.

---

## 25. University and School Deployment Model

The platform should support **institution-owned deployment** for universities, colleges, schools, and remote-learning organizations. An institution can install a dedicated environment in its own cloud subscription, private cloud, or approved data center while students access classes remotely through a standard web browser.

### Deployment objectives

- One installation can serve multiple faculties, departments, schools, courses, teachers, and student cohorts.
- Support Internet-based remote students without requiring a desktop application.
- Allow the institution to retain control of users, course materials, teacher voice profiles, learning records, logs, retention policies, and AI-provider configuration.
- Support cloud-managed, institution-managed, and hybrid AI services.
- Separate each institution's data and configuration when the product is offered as a multi-tenant service.
- Scale application, media, retrieval, LLM, and voice workloads independently.

### Institution deployment topology

```text
                   UNIVERSITY / SCHOOL
                           |
             +-------------+-------------+
             |                           |
        Administrators                Teachers
             |                           |
             +-------------+-------------+
                           |
                    Admin / Studio UI
                           |
                           v
                  Institution Backend
                           |
        +------------------+------------------+
        |                  |                  |
        v                  v                  v
 Identity / SSO       Course Content      Teacher Profiles
        |                  |                  |
        +------------------+------------------+
                           |
                           v
                  AI Teacher Platform
                           |
          +----------------+----------------+
          |                                 |
          v                                 v
     School Network                    Public Internet
          |                                 |
          v                                 v
 Classroom displays                Remote students
                                         |
                                         v
                                  Browser Classroom
```

### Recommended production installation

```text
Internet / Campus Network
          |
          v
DNS + TLS + WAF / Front Door
          |
          +--------------------+--------------------+
          |                    |                    |
          v                    v                    v
   Web Classroom          Admin Portal        Teacher Studio
          |                    |                    |
          +--------------------+--------------------+
                               |
                               v
                         API Gateway
                               |
                               v
                    Container Platform / AKS
                               |
       +-----------------------+-----------------------+
       |            |            |          |          |
       v            v            v          v          v
   Teacher       Session      Knowledge    Class      Voice
 Orchestrator    Service       Service    Manager    Service
       |            |            |          |          |
       +------------+------------+----------+----------+
                               |
                +--------------+--------------+
                |              |              |
                v              v              v
            PostgreSQL        Redis       AI Search
                |                             |
                +--------------+--------------+
                               |
                               v
                         Blob Storage

External or private AI capacity:

LLM Provider / Institution LLM
OmniVoice GPU Pool
Speech/Realtime Media Service
```

---

## 26. Institutional Tenant Model

Every installation should define an `institution_id`. If a central SaaS installation hosts several schools, this becomes the primary isolation boundary.

```text
Institution
  |
  +-- Faculty / School
  |      |
  |      +-- Department
  |             |
  |             +-- Program
  |                    |
  |                    +-- Course
  |                           |
  |                           +-- Class / Section
  |                                  |
  |                                  +-- Teacher
  |                                  +-- Students
  |
  +-- Institution Administrators
```

Recommended identifiers:

```text
institution_id
faculty_id
department_id
program_id
course_id
class_id
teacher_id
student_id
```

Authorization checks must include the institution boundary so users from one institution cannot retrieve another institution's courses, RAG chunks, voice profiles, records, or classroom sessions.

---

## 27. Identity, SSO, and Roles

The platform should integrate with the institution's existing identity system instead of creating a completely separate user directory whenever possible.

Supported integration patterns should include:

```text
OIDC / OAuth 2.0
SAML 2.0 through an identity gateway where required
Microsoft Entra ID / institutional identity provider
Local accounts only as an optional fallback
```

Recommended roles:

```text
Platform Administrator
Institution Administrator
IT Operator
Course Administrator
Teacher
Teaching Assistant
Student
Auditor / Read-only Operator
```

Example permission model:

```text
Institution Administrator
  -> manage institution configuration
  -> manage integrations
  -> view institution-wide usage

Teacher
  -> create/manage assigned courses
  -> upload teaching material
  -> configure authorized teacher voice
  -> view students in assigned classes
  -> review learning analytics

Student
  -> join registered classes
  -> ask questions
  -> take quizzes
  -> view own progress
```

---

## 28. Remote Teaching and Classroom Delivery

A single course may support both individually personalized AI sessions and scheduled group classes.

### Personal remote class

```text
1 student
    |
    v
1 personalized AI teacher session
```

The teacher can adapt pacing, examples, questions, and review based on the individual Student Model.

### Scheduled group class

```text
                     AI Teacher Session
                            |
                    shared lesson/audio
                            |
          +-----------------+-----------------+
          |                 |                 |
       Student A         Student B         Student N
```

For group classes, avoid generating a separate main lecture audio stream for every student. Generate one primary teacher stream per class and distribute it through the realtime/media layer. Student questions can enter a moderated question queue.

### Question modes

An institution should be able to configure:

```text
FREE_INTERRUPT
RAISE_HAND
TEACHER_APPROVED
TEXT_ONLY
QUESTION_QUEUE
QUIZ_ONLY_DURING_LECTURE
```

This prevents a large remote class from becoming unusable when many students speak simultaneously.

---

## 29. Course Provisioning Workflow

```text
Administrator creates course
          |
          v
Assign teacher(s)
          |
          v
Import/enroll students
          |
          v
Upload PDF/PPTX/DOCX/materials
          |
          v
Asynchronous document ingestion
          |
          v
RAG index created
          |
          v
Generate/review lesson plan
          |
          v
Configure presentation
          |
          v
Select authorized teacher voice profile
          |
          v
Teacher previews AI lesson
          |
          v
Approve/publish course
          |
          v
Students can attend remotely
```

A course should have lifecycle states such as:

```text
DRAFT
PROCESSING
REVIEW_REQUIRED
PUBLISHED
ACTIVE
ARCHIVED
```

High-impact course changes should return a published course to `REVIEW_REQUIRED` before students receive the new content.

---

## 30. Teacher Studio

Universities and schools need an authoring and review environment in addition to the student classroom.

The Teacher Studio should support:

- Upload and organize course resources.
- Preview extracted document content and RAG citations.
- Configure or edit the generated lesson plan.
- Preview slides and dynamic visuals.
- Select teaching language and difficulty.
- Configure quiz and assessment rules.
- Enroll an authorized teacher voice profile.
- Preview generated speech before publishing.
- Define interruption/question policy.
- Publish a versioned course.
- Review questions the AI could not answer confidently.
- Review student misconceptions and learning analytics.

```text
Teacher
   |
   v
Teacher Studio
   |
   +--> Course Materials
   +--> Lesson Plan
   +--> RAG Preview
   +--> Voice Profile
   +--> Presentation Preview
   +--> Quiz Configuration
   +--> Publish / Version
```

---

## 31. Installation Profiles

The same software should support several deployment profiles.

### Profile A: Managed Cloud

Best for institutions that do not want to operate AI infrastructure.

```text
Institution
     |
     v
Managed AI Teacher Cloud
     |
     +--> Managed database
     +--> Managed Redis
     +--> Managed search
     +--> Managed LLM
     +--> Managed OmniVoice GPUs
```

### Profile B: Institution-Owned Cloud

Recommended for universities with an IT/cloud team.

```text
University Cloud Subscription
     |
     +--> Kubernetes / AKS
     +--> PostgreSQL
     +--> Redis
     +--> Search
     +--> Object Storage
     +--> Monitoring
     |
     +--> External or private LLM
     +--> OmniVoice GPU capacity
```

### Profile C: Hybrid

Useful when student/course data must remain under institutional control but some model inference may use external AI services.

```text
Institution Infrastructure
     |
     +--> Identity
     +--> Database
     +--> Course Documents
     +--> Learning Records
     +--> RAG/Search
     |
     +---- approved outbound AI calls ----> LLM service
     +---- approved outbound voice calls -> Voice service
```

### Profile D: Private / On-Premises

For institutions requiring maximum infrastructure control.

```text
University Data Center
     |
     +--> Kubernetes
     +--> PostgreSQL
     +--> Redis
     +--> Object Storage
     +--> Vector Search
     +--> Local LLM inference GPUs
     +--> OmniVoice GPUs
     +--> Monitoring
```

Private deployment requires significantly more GPU capacity planning and operational maturity. It should be offered only after the cloud architecture and load characteristics are well measured.

---

## 32. Installation Package

An institution-ready release should be delivered as versioned deployment artifacts rather than manual source-code installation.

Recommended package:

```text
release/
├── helm/
│   └── ai-teacher/
├── containers/
│   └── image-manifest.txt
├── infra/
│   ├── azure-bicep/
│   └── terraform/
├── config/
│   ├── values.example.yaml
│   └── environment.example
├── migrations/
├── scripts/
│   ├── preflight.sh
│   ├── install.sh
│   ├── upgrade.sh
│   ├── backup.sh
│   └── restore.sh
├── docs/
│   ├── INSTALL.md
│   ├── ADMIN_GUIDE.md
│   ├── OPERATIONS.md
│   ├── SECURITY.md
│   └── DISASTER_RECOVERY.md
└── VERSION
```

The production installation should support automated infrastructure provisioning and Helm-based application deployment where Kubernetes is used.

---

## 33. Configuration Contract

Keep environment-specific values outside application images. A deployment configuration should define at least:

```yaml
institution:
  id: university-001
  display_name: Example University

public:
  classroom_url: https://classroom.example.edu
  studio_url: https://studio.example.edu
  api_url: https://api.example.edu

auth:
  provider: oidc
  issuer: https://institution-idp.example.edu
  client_id: ai-teacher

storage:
  postgres_secret_ref: ai-teacher-postgres
  redis_secret_ref: ai-teacher-redis
  object_storage_secret_ref: ai-teacher-storage

rag:
  provider: azure_ai_search
  endpoint_secret_ref: ai-teacher-search

llm:
  provider: configured-provider
  credential_secret_ref: ai-teacher-llm

voice:
  provider: omnivoice
  execution_mode: gpu_pool

realtime:
  webrtc_enabled: true
  websocket_enabled: true

retention:
  classroom_event_days: 90
  transcript_days: 30
```

Secrets must be referenced from the deployment secret manager and must not be committed in configuration files.

---

## 34. Installation Flow

A repeatable institutional deployment should follow this sequence.

```text
1. Infrastructure preflight
      |
      +--> DNS available
      +--> TLS certificates available
      +--> Kubernetes capacity available
      +--> Database available
      +--> Redis available
      +--> Object storage available
      +--> Search available
      +--> LLM quota/capacity validated
      +--> OmniVoice GPU capacity validated
      |
2. Provision infrastructure
      |
3. Create secrets / managed identities
      |
4. Deploy database migrations
      |
5. Deploy backend services
      |
6. Deploy Web Classroom and Teacher Studio
      |
7. Configure SSO
      |
8. Configure storage/RAG/LLM/voice providers
      |
9. Run health checks
      |
10. Run one synthetic classroom
      |
11. Run concurrency/load test
      |
12. Administrator acceptance
      |
13. Production release
```

The installer should fail early when a hard dependency or required capacity is unavailable.

---

## 35. Network and Firewall Requirements

The architecture must be friendly to campus networks and remote students behind home routers/firewalls.

Logical zones:

```text
PUBLIC ZONE
  Web Classroom
  API Gateway
  Realtime ingress
       |
       v
PRIVATE APPLICATION ZONE
  Teacher Orchestrator
  Session Service
  Knowledge Service
  Voice Service
       |
       v
PRIVATE DATA ZONE
  PostgreSQL
  Redis
  Search
  Object Storage/private endpoints where applicable
```

Only required public endpoints should be Internet reachable. Database, Redis, internal workers, and administrative infrastructure should remain private.

The institution should validate outbound connectivity required by its configured LLM, search, identity, telemetry, and voice providers.

---

## 36. Availability and Disaster Recovery

A remote teaching platform becomes a classroom dependency, so production installations need recoverability.

At minimum:

- Multiple application replicas for critical stateless services.
- Readiness and liveness probes.
- Automatic pod/process restart.
- Database backups and point-in-time recovery where available.
- Object-storage versioning/backup policy.
- RAG indexes reproducible from original course documents.
- Infrastructure-as-code stored in version control.
- Documented restore procedure.
- Session recovery from Redis/persistent checkpoints where appropriate.
- Graceful user notification when an external AI provider is degraded.

Suggested recovery hierarchy:

```text
Source course files -> authoritative content backup
PostgreSQL          -> authoritative application records
Object Storage      -> course/voice/media assets
Redis               -> disposable/recoverable realtime state
Search Index        -> rebuildable from source content
Application Pods    -> disposable and re-deployable
```

---

## 37. Observability for Institution IT Teams

Provide an operations dashboard that answers:

```text
Is the platform healthy?
How many classes are live?
How many students are connected?
Are students hearing the teacher?
Is LLM latency increasing?
Is voice generation queued?
Is RAG failing?
Are GPUs saturated?
Are any classes repeatedly reconnecting?
What is today's AI usage/cost?
```

Institution-level metrics should include:

```text
active_classes
connected_students
classes_started_total
class_start_failures
question_count
webrtc_connection_success_rate
audio_time_to_first_frame
llm_time_to_first_token
rag_latency
tts_time_to_first_audio
tts_queue_depth
gpu_utilization
postgres_connections
redis_latency
http_5xx_rate
websocket_disconnect_rate
cost_per_teaching_hour
```

Logs and traces should carry correlation fields such as:

```text
institution_id
class_id
course_id
session_id
request_id
trace_id
```

Do not place unnecessary sensitive student content in logs.

---

## 38. Capacity Profiles for Schools and Universities

Deployment should be sized from measured concurrency, not total enrollment. Example planning profiles are starting points for load testing, not guaranteed production specifications.

```text
SMALL SCHOOL
  1-20 simultaneous AI classes
  hundreds to low thousands of registered users
  modest application replicas
  managed LLM recommended
  small/managed voice capacity

MEDIUM INSTITUTION
  20-100 simultaneous AI classes
  thousands of users
  horizontally scaled backend
  dedicated/managed search capacity
  Redis + managed PostgreSQL
  dedicated voice worker pool

LARGE UNIVERSITY
  100-500+ simultaneous AI classes
  potentially tens of thousands of connected/registered users
  Kubernetes autoscaling
  dedicated database/search planning
  realtime media scaling
  LLM throughput/quota planning
  multi-GPU OmniVoice pool
  centralized observability and cost controls
```

For group classes, calculate both:

```text
Concurrent AI teacher sessions
AND
Concurrent connected student browsers
```

These numbers stress different parts of the platform.

---

## 39. LMS and Student Information System Integration

Design institutional integration through adapters so the platform does not depend on one vendor.

```text
Institution LMS / SIS
        |
        v
Integration Adapter
        |
        +--> Courses
        +--> Class rosters
        +--> Enrollments
        +--> Assignment/quiz results where approved
        +--> Completion state
        |
        v
AI Teacher Platform
```

Possible interfaces:

```text
REST APIs
Webhooks
CSV import/export for initial deployment
LTI-compatible integration where required
Institution-specific connectors
```

Registration and grading remain authoritative either in the AI Teacher database or the institution's designated system of record. The integration contract must clearly define which system owns each field.

---

## 40. Remote Education Operations Workflow

### Before semester

```text
IT deploys/upgrades platform
        |
Identity integration verified
        |
Course roster synchronized
        |
Teachers prepare/approve AI courses
        |
Voice authorizations verified
        |
Load test performed
```

### During semester

```text
Students join remotely
        |
AI Teacher presents
        |
Questions / quizzes / progress
        |
Operational telemetry monitored
        |
Teachers review unresolved questions
```

### End of course

```text
Finalize attendance
        |
Finalize required assessments
        |
Calculate completion deterministically
        |
Sync result to LMS/SIS if configured
        |
Generate approved completion record/certificate
        |
Archive course version and retention-controlled data
```

---

## 41. Institutional Production Readiness Checklist

Before a university or school launches the platform, verify:

### Identity and access

- [ ] SSO works for administrators, teachers, and students.
- [ ] Role mappings are reviewed.
- [ ] Institution/tenant isolation is tested.
- [ ] Service credentials and secrets are externally managed.

### Course and AI quality

- [ ] Course documents are indexed successfully.
- [ ] RAG answers contain valid source references.
- [ ] Teacher has reviewed generated lesson structure.
- [ ] Unsupported questions have a safe fallback path.
- [ ] Quiz and completion rules are deterministic and approved.

### Voice

- [ ] Voice owner authorization is recorded.
- [ ] Teacher can review the voice before publication.
- [ ] Voice reference data is access controlled.
- [ ] Voice profile can be revoked/deleted.

### Realtime classroom

- [ ] WebRTC works on the target campus network.
- [ ] Remote/home-network testing is completed.
- [ ] Student interruption mode behaves as configured.
- [ ] Teacher audio recovers from brief network interruptions.
- [ ] Session resume has been tested.

### Scale

- [ ] Expected peak concurrent classes are load tested.
- [ ] Expected peak concurrent students are load tested.
- [ ] LLM quota/capacity is verified.
- [ ] OmniVoice GPU capacity is benchmarked.
- [ ] Search latency is tested against the real course corpus.

### Operations

- [ ] Dashboards and alerts are configured.
- [ ] Backups are configured and restore has been tested.
- [ ] Upgrade/rollback procedure is documented.
- [ ] Disaster recovery responsibilities are assigned.
- [ ] AI usage and cost budgets/alerts are configured.

### Privacy and governance

- [ ] Student-data retention is configured.
- [ ] Transcript/recording policy is configured.
- [ ] Data residency requirements have been reviewed by the institution.
- [ ] Teacher voice consent/authorization policy is approved.
- [ ] Access/audit logging policy is approved.
- [ ] Human review/escalation process is defined for important academic disputes.

---

## 42. Product Packaging Recommendation

The platform can be presented to institutions as four user-facing products backed by one platform.

```text
                         AI TEACHER PLATFORM
                                  |
           +----------------------+----------------------+
           |                      |                      |
           v                      v                      v
     Classroom Portal       Teacher Studio          Admin Portal
       for students          for educators            for IT
           |                      |                      |
           +----------------------+----------------------+
                                  |
                                  v
                           Platform APIs
                                  |
                                  v
                     Teacher Orchestrator Core
```

Optional product names can be assigned later, but these functional boundaries should remain even in a single deployment.

---

## 43. Institutional Architecture Summary

The university/school edition should be installable without changing the core teacher architecture. Institution-specific concerns are added around it:

```text
             UNIVERSITY / SCHOOL ENVIRONMENT
                          |
       +------------------+------------------+
       |                  |                  |
      SSO             LMS / SIS          IT Admin
       |                  |                  |
       +------------------+------------------+
                          |
                          v
                  AI TEACHER PLATFORM
                          |
              +-----------+-----------+
              |                       |
              v                       v
       Teacher Studio            Web Classroom
                                      |
                               Remote Students
                          |
                          v
                 Teacher Orchestrator
                          |
       +------------------+------------------+
       |                  |                  |
       v                  v                  v
 Lesson Engine       Student Model      Knowledge/RAG
       |                  |                  |
       +------------------+------------------+
                          |
                          v
                       LLM Router
                          |
                     +----+----+
                     |         |
                     v         v
                 OmniVoice   Presentation
                     |         |
                     +----+----+
                          |
                          v
                    Remote Classroom

Platform foundation:
  PostgreSQL + Redis + Search + Object Storage
  Container platform + Realtime media + Observability
  Backup/restore + Security + Tenant isolation
```

This model allows the same product to run as a managed service for a small school, in a university-owned cloud environment, or eventually as a private/on-premises installation without rewriting the Teacher Orchestrator or classroom application.
