from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from pydantic import BaseModel
from datetime import datetime
import qrcode
import io
import base64
from typing import List, Optional
import os

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./quiz_app.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Database Models
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    uni = Column(String(50), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    participations = relationship("Participation", back_populates="user")

class Quiz(Base):
    __tablename__ = "quizzes"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    area = Column(String(100), nullable=False)
    description = Column(Text)
    is_active = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    questions = relationship("Question", back_populates="quiz", cascade="all, delete-orphan")
    participations = relationship("Participation", back_populates="quiz")

class Question(Base):
    __tablename__ = "questions"
    
    id = Column(Integer, primary_key=True, index=True)
    quiz_id = Column(Integer, ForeignKey("quizzes.id"))
    question_text = Column(Text, nullable=False)
    question_order = Column(Integer, nullable=False)
    time_limit = Column(Integer, default=30)  # seconds
    
    quiz = relationship("Quiz", back_populates="questions")
    answers = relationship("Answer", back_populates="question", cascade="all, delete-orphan")

class Answer(Base):
    __tablename__ = "answers"
    
    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("questions.id"))
    answer_text = Column(String(500), nullable=False)
    is_correct = Column(Boolean, default=False)
    answer_order = Column(Integer, nullable=False)
    
    question = relationship("Question", back_populates="answers")

class Participation(Base):
    __tablename__ = "participations"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    quiz_id = Column(Integer, ForeignKey("quizzes.id"))
    score = Column(Integer, default=0)
    total_questions = Column(Integer, default=0)
    completed = Column(Boolean, default=False)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    user = relationship("User", back_populates="participations")
    quiz = relationship("Quiz", back_populates="participations")
    responses = relationship("UserResponse", back_populates="participation", cascade="all, delete-orphan")

class UserResponse(Base):
    __tablename__ = "user_responses"
    
    id = Column(Integer, primary_key=True, index=True)
    participation_id = Column(Integer, ForeignKey("participations.id"))
    question_id = Column(Integer, ForeignKey("questions.id"))
    answer_id = Column(Integer, ForeignKey("answers.id"))
    response_time = Column(Integer)  # milliseconds
    is_correct = Column(Boolean, default=False)
    answered_at = Column(DateTime, default=datetime.utcnow)
    
    participation = relationship("Participation", back_populates="responses")
    question = relationship("Question")   # 🔹 agregar
    answer = relationship("Answer")       # 🔹 agregar

# Pydantic Models (NOMBRES CORREGIDOS AQUÍ)
class UserCreate(BaseModel):
    uni: str
    name: str

class UserOut(BaseModel):
    id: int
    uni: str
    name: str
    created_at: datetime

class QuizCreate(BaseModel):
    title: str
    area: str
    description: Optional[str] = None

class QuizUpdate(BaseModel):
    title: Optional[str] = None
    area: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

class AnswerCreate(BaseModel):
    answer_text: str
    is_correct: bool
    answer_order: int

class QuestionCreate(BaseModel):
    question_text: str
    question_order: int
    time_limit: int = 30
    answers: List[AnswerCreate]

class QuizOut(BaseModel):
    id: int
    title: str
    area: str
    description: Optional[str]
    is_active: bool
    created_at: datetime

class AnswerOut(BaseModel):
    id: int
    answer_text: str
    answer_order: int

class QuestionOut(BaseModel):
    id: int
    question_text: str
    question_order: int
    time_limit: int
    answers: List[AnswerOut]

class QuizDetailOut(BaseModel):
    id: int
    title: str
    area: str
    description: Optional[str]
    is_active: bool
    questions: List[QuestionOut]

class SubmitAnswer(BaseModel):
    question_id: int
    answer_id: int
    response_time: int

class ParticipationOut(BaseModel):
    id: int
    quiz_title: str
    score: int
    total_questions: int
    completed: bool
    started_at: datetime
    completed_at: Optional[datetime]

# Create tables
Base.metadata.create_all(bind=engine)

# FastAPI app
app = FastAPI(title="Quiz System API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# User endpoints
@app.post("/api/users/", response_model=UserOut)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.uni == user.uni).first()
    if db_user:
        return db_user
    
    db_user = User(uni=user.uni, name=user.name)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@app.get("/api/users/{uni}", response_model=UserOut)
def get_user_by_uni(uni: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.uni == uni).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return user

@app.get("/api/users/{uni}/participations", response_model=List[ParticipationOut])
def get_user_participations(uni: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.uni == uni).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    participations = db.query(Participation).filter(Participation.user_id == user.id).all()
    result = []
    for p in participations:
        result.append({
            "id": p.id,
            "quiz_title": p.quiz.title,
            "score": p.score,
            "total_questions": p.total_questions,
            "completed": p.completed,
            "started_at": p.started_at,
            "completed_at": p.completed_at
        })
    return result

# Quiz endpoints
@app.post("/api/quizzes/", response_model=QuizOut)
def create_quiz(quiz: QuizCreate, db: Session = Depends(get_db)):
    db_quiz = Quiz(title=quiz.title, area=quiz.area, description=quiz.description)
    db.add(db_quiz)
    db.commit()
    db.refresh(db_quiz)
    return db_quiz

@app.get("/api/quizzes/", response_model=List[QuizOut])
def get_quizzes(active_only: bool = False, db: Session = Depends(get_db)):
    query = db.query(Quiz)
    if active_only:
        query = query.filter(Quiz.is_active == True)
    return query.all()

@app.get("/api/quizzes/{quiz_id}", response_model=QuizDetailOut)
def get_quiz(quiz_id: int, db: Session = Depends(get_db)):
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz no encontrado")
    
    # Convert to response format
    questions = []
    for q in quiz.questions:
        answers = [{"id": a.id, "answer_text": a.answer_text, "answer_order": a.answer_order} 
                  for a in sorted(q.answers, key=lambda x: x.answer_order)]
        questions.append({
            "id": q.id,
            "question_text": q.question_text,
            "question_order": q.question_order,
            "time_limit": q.time_limit,
            "answers": answers
        })
    
    return {
        "id": quiz.id,
        "title": quiz.title,
        "area": quiz.area,
        "description": quiz.description,
        "is_active": quiz.is_active,
        "questions": sorted(questions, key=lambda x: x["question_order"])
    }

@app.put("/api/quizzes/{quiz_id}", response_model=QuizOut)
def update_quiz(quiz_id: int, quiz_update: QuizUpdate, db: Session = Depends(get_db)):
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz no encontrado")
    
    for field, value in quiz_update.dict(exclude_unset=True).items():
        setattr(quiz, field, value)
    
    db.commit()
    db.refresh(quiz)
    return quiz

@app.delete("/api/quizzes/{quiz_id}")
def delete_quiz(quiz_id: int, db: Session = Depends(get_db)):
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz no encontrado")
    
    db.delete(quiz)
    db.commit()
    return {"message": "Quiz eliminado exitosamente"}

# Question endpoints
@app.post("/api/quizzes/{quiz_id}/questions")
def add_question(quiz_id: int, question: QuestionCreate, db: Session = Depends(get_db)):
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz no encontrado")
    
    db_question = Question(
        quiz_id=quiz_id,
        question_text=question.question_text,
        question_order=question.question_order,
        time_limit=question.time_limit
    )
    db.add(db_question)
    db.commit()
    db.refresh(db_question)
    
    # Add answers
    for answer in question.answers:
        db_answer = Answer(
            question_id=db_question.id,
            answer_text=answer.answer_text,
            is_correct=answer.is_correct,
            answer_order=answer.answer_order
        )
        db.add(db_answer)
    
    db.commit()
    return {"message": "Pregunta agregada exitosamente"}

# Participation endpoints
@app.post("/api/participate/{quiz_id}")
def start_participation(quiz_id: int, uni: str, db: Session = Depends(get_db)):
    # Get or create user
    user = db.query(User).filter(User.uni == uni).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado. Registrate primero.")
    
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if not quiz or not quiz.is_active:
        raise HTTPException(status_code=404, detail="Quiz no disponible")
    
    # Check if already participating
    existing = db.query(Participation).filter(
        Participation.user_id == user.id,
        Participation.quiz_id == quiz_id,
        Participation.completed == False
    ).first()
    
    if existing:
        return {"participation_id": existing.id, "message": "Continuando participación existente"}
    
    # Create new participation
    total_questions = len(quiz.questions)
    participation = Participation(
        user_id=user.id,
        quiz_id=quiz_id,
        total_questions=total_questions
    )
    db.add(participation)
    db.commit()
    db.refresh(participation)
    
    return {"participation_id": participation.id, "total_questions": total_questions}

@app.post("/api/participate/{participation_id}/submit")
def submit_answer(participation_id: int, answer: SubmitAnswer, db: Session = Depends(get_db)):
    participation = db.query(Participation).filter(Participation.id == participation_id).first()
    if not participation:
        raise HTTPException(status_code=404, detail="Participación no encontrada")
    
    # Check if already answered this question
    existing_response = db.query(UserResponse).filter(
        UserResponse.participation_id == participation_id,
        UserResponse.question_id == answer.question_id
    ).first()
    
    if existing_response:
        raise HTTPException(status_code=400, detail="Ya respondiste esta pregunta")
    
    # Get correct answer
    correct_answer = db.query(Answer).filter(
        Answer.question_id == answer.question_id,
        Answer.is_correct == True
    ).first()
    
    is_correct = (answer.answer_id == correct_answer.id) if correct_answer else False
    
    # Save response
    user_response = UserResponse(
        participation_id=participation_id,
        question_id=answer.question_id,
        answer_id=answer.answer_id,
        response_time=answer.response_time,
        is_correct=is_correct
    )
    db.add(user_response)
    
    # Update score
    if is_correct:
        participation.score += 1
    
    db.commit()
    
    return {"correct": is_correct, "current_score": participation.score}

@app.post("/api/participate/{participation_id}/complete")
def complete_participation(participation_id: int, db: Session = Depends(get_db)):
    participation = db.query(Participation).filter(Participation.id == participation_id).first()
    if not participation:
        raise HTTPException(status_code=404, detail="Participación no encontrada")
    
    participation.completed = True
    participation.completed_at = datetime.utcnow()
    db.commit()
    
    return {
        "score": participation.score,
        "total_questions": participation.total_questions,
        "percentage": round((participation.score / participation.total_questions) * 100, 2)
    }

# QR Code generation
@app.get("/api/generate-qr/{quiz_id}")
def generate_qr(quiz_id: int, db: Session = Depends(get_db)):
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz no encontrado")
    
    # Generate QR with quiz URL
    quiz_url = f"https://your-domain.com/quiz/{quiz_id}"  # Replace with your domain
    
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(quiz_url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to base64
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    img_str = base64.b64encode(buffer.getvalue()).decode()
    
    return {
        "quiz_id": quiz_id,
        "quiz_title": quiz.title,
        "qr_code": f"data:image/png;base64,{img_str}",
        "url": quiz_url
    }

@app.get("/api/responses")
def get_all_responses(db: Session = Depends(get_db)):
    responses = db.query(UserResponse).all()
    result = []
    for r in responses:
        result.append({
            "participation_id": r.participation_id,
            "user_uni": r.participation.user.uni,
            "quiz_title": r.participation.quiz.title,
            "question_text": r.question.question_text,
            "answer_text": r.answer.answer_text,
            "is_correct": r.is_correct,
            "response_time": r.response_time,
            "answered_at": r.answered_at
        })
    return result
    
# Health check
@app.get("/")
def health_check():
    return {"status": "Quiz System API is running", "version": "1.0.0"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)