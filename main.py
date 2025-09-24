from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
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
    time_limit = Column(Integer, default=30)
    
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
    response_time = Column(Integer)
    is_correct = Column(Boolean, default=False)
    answered_at = Column(DateTime, default=datetime.utcnow)
    
    participation = relationship("Participation", back_populates="responses")

# Pydantic Models
class UserCreate(BaseModel):
    uni: str
    name: str

class UserUpdate(BaseModel):
    name: Optional[str] = None

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

class QuestionUpdate(BaseModel):
    question_text: Optional[str] = None
    question_order: Optional[int] = None
    time_limit: Optional[int] = None
    answers: Optional[List[AnswerCreate]] = None

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

class QuizOut(BaseModel):
    id: int
    title: str
    area: str
    description: Optional[str]
    is_active: bool
    created_at: datetime

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
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Root endpoint
@app.get("/")
def read_root():
    return FileResponse("static/index.html")

# User endpoints
@app.post("/api/users/", response_model=UserOut)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    # Check if user already exists
    db_user = db.query(User).filter(User.uni == user.uni).first()
    if db_user:
        return db_user
    
    # Create new user
    db_user = User(uni=user.uni, name=user.name)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@app.get("/api/users/", response_model=List[UserOut])
def get_all_users(db: Session = Depends(get_db)):
    users = db.query(User).all()
    return users

@app.get("/api/users/{uni}", response_model=UserOut)
def get_user_by_uni(uni: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.uni == uni).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return user

@app.put("/api/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, user_update: UserUpdate, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    for field, value in user_update.dict(exclude_unset=True).items():
        setattr(user, field, value)
    
    db.commit()
    db.refresh(user)
    return user

@app.delete("/api/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    db.delete(user)
    db.commit()
    return {"message": "Usuario eliminado exitosamente"}

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
    for q in sorted(quiz.questions, key=lambda x: x.question_order):
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
        "questions": questions
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

@app.get("/api/questions/{question_id}")
def get_question(question_id: int, db: Session = Depends(get_db)):
    question = db.query(Question).filter(Question.id == question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Pregunta no encontrada")
    
    answers = [{"id": a.id, "answer_text": a.answer_text, "is_correct": a.is_correct, "answer_order": a.answer_order} 
              for a in sorted(question.answers, key=lambda x: x.answer_order)]
    
    return {
        "id": question.id,
        "question_text": question.question_text,
        "question_order": question.question_order,
        "time_limit": question.time_limit,
        "answers": answers
    }

@app.put("/api/questions/{question_id}")
def update_question(question_id: int, question_update: QuestionUpdate, db: Session = Depends(get_db)):
    question = db.query(Question).filter(Question.id == question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Pregunta no encontrada")
    
    # Update basic fields
    if question_update.question_text is not None:
        question.question_text = question_update.question_text
    if question_update.question_order is not None:
        question.question_order = question_update.question_order
    if question_update.time_limit is not None:
        question.time_limit = question_update.time_limit
    
    # Update answers if provided
    if question_update.answers is not None:
        # Delete old answers
        db.query(Answer).filter(Answer.question_id == question_id).delete()
        
        # Create new answers
        for answer in question_update.answers:
            db_answer = Answer(
                question_id=question_id,
                answer_text=answer.answer_text,
                is_correct=answer.is_correct,
                answer_order=answer.answer_order
            )
            db.add(db_answer)
    
    db.commit()
    db.refresh(question)
    return {"message": "Pregunta actualizada exitosamente"}

@app.delete("/api/questions/{question_id}")
def delete_question(question_id: int, db: Session = Depends(get_db)):
    question = db.query(Question).filter(Question.id == question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Pregunta no encontrada")
    
    db.delete(question)
    db.commit()
    return {"message": "Pregunta eliminada exitosamente"}

# Participation endpoints
@app.get("/api/users/{uni}/quiz/{quiz_id}/status")
def get_participation_status(uni: str, quiz_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.uni == uni).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    participation = db.query(Participation).filter(
        Participation.user_id == user.id,
        Participation.quiz_id == quiz_id
    ).first()
    
    if not participation:
        return {"status": "not_started", "can_participate": True}
    
    if participation.completed:
        return {
            "status": "completed",
            "can_participate": False,
            "score": participation.score,
            "total_questions": participation.total_questions,
            "percentage": round((participation.score / participation.total_questions) * 100, 2) if participation.total_questions > 0 else 0,
            "completed_at": participation.completed_at
        }
    
    return {
        "status": "in_progress", 
        "can_participate": True,
        "participation_id": participation.id,
        "current_score": participation.score
    }

@app.post("/api/participate/{quiz_id}")
def start_participation(quiz_id: int, uni: str, db: Session = Depends(get_db)):
    # Get user
    user = db.query(User).filter(User.uni == uni).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if not quiz or not quiz.is_active:
        raise HTTPException(status_code=404, detail="Quiz no disponible")
    
    # Check if already completed
    completed_participation = db.query(Participation).filter(
        Participation.user_id == user.id,
        Participation.quiz_id == quiz_id,
        Participation.completed == True
    ).first()
    
    if completed_participation:
        raise HTTPException(
            status_code=400, 
            detail=f"Ya completaste este quiz. Puntuación: {completed_participation.score}/{completed_participation.total_questions}"
        )
    
    # Check for existing incomplete participation
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
    
    # Check if already answered
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
        "percentage": round((participation.score / participation.total_questions) * 100, 2) if participation.total_questions > 0 else 0
    }

@app.get("/api/participations/")
def get_all_participations(completed_only: bool = False, db: Session = Depends(get_db)):
    query = db.query(Participation)
    if completed_only:
        query = query.filter(Participation.completed == True)
    
    participations = query.all()
    
    result = []
    for p in participations:
        result.append({
            "id": p.id,
            "user_name": p.user.name,
            "user_uni": p.user.uni,
            "quiz_title": p.quiz.title,
            "score": p.score,
            "total_questions": p.total_questions,
            "percentage": round((p.score / p.total_questions * 100), 2) if p.total_questions > 0 else 0,
            "completed": p.completed,
            "started_at": p.started_at,
            "completed_at": p.completed_at
        })
    
    return result

@app.delete("/api/participations/{participation_id}")
def delete_participation(participation_id: int, db: Session = Depends(get_db)):
    participation = db.query(Participation).filter(Participation.id == participation_id).first()
    if not participation:
        raise HTTPException(status_code=404, detail="Participación no encontrada")
    
    db.delete(participation)
    db.commit()
    return {"message": "Participación eliminada exitosamente"}

# Statistics endpoints
@app.get("/api/statistics/dashboard")
def get_dashboard_statistics(db: Session = Depends(get_db)):
    total_quizzes = db.query(Quiz).count()
    active_quizzes = db.query(Quiz).filter(Quiz.is_active == True).count()
    total_users = db.query(User).count()
    total_participations = db.query(Participation).count()
    completed_participations = db.query(Participation).filter(Participation.completed == True).count()
    
    return {
        "total_quizzes": total_quizzes,
        "active_quizzes": active_quizzes,
        "inactive_quizzes": total_quizzes - active_quizzes,
        "total_users": total_users,
        "total_participations": total_participations,
        "completed_participations": completed_participations,
        "completion_rate": round((completed_participations / total_participations * 100), 2) if total_participations > 0 else 0
    }

@app.get("/api/statistics/quiz/{quiz_id}")
def get_quiz_statistics(quiz_id: int, db: Session = Depends(get_db)):
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz no encontrado")
    
    participations = db.query(Participation).filter(Participation.quiz_id == quiz_id).all()
    completed_participations = [p for p in participations if p.completed]
    
    total_participations = len(participations)
    total_completed = len(completed_participations)
    
    if total_completed > 0:
        avg_score = sum(p.score for p in completed_participations) / total_completed
        avg_percentage = sum((p.score / p.total_questions * 100) for p in completed_participations) / total_completed
    else:
        avg_score = 0
        avg_percentage = 0
    
    return {
        "quiz_id": quiz_id,
        "quiz_title": quiz.title,
        "total_participations": total_participations,
        "completed_participations": total_completed,
        "completion_rate": round((total_completed / total_participations * 100), 2) if total_participations > 0 else 0,
        "average_score": round(avg_score, 2),
        "average_percentage": round(avg_percentage, 2),
        "total_questions": len(quiz.questions)
    }

# Bulk operations
@app.post("/api/quizzes/bulk-toggle")
def bulk_toggle_quizzes(quiz_ids: List[int], is_active: bool, db: Session = Depends(get_db)):
    updated = db.query(Quiz).filter(Quiz.id.in_(quiz_ids)).update(
        {Quiz.is_active: is_active}, synchronize_session=False
    )
    db.commit()
    
    return {"message": f"{updated} quizzes {'activados' if is_active else 'desactivados'} exitosamente"}

@app.delete("/api/quizzes/bulk-delete")
def bulk_delete_quizzes(quiz_ids: List[int], db: Session = Depends(get_db)):
    deleted = db.query(Quiz).filter(Quiz.id.in_(quiz_ids)).delete(synchronize_session=False)
    db.commit()
    
    return {"message": f"{deleted} quizzes eliminados exitosamente"}


# Agrega estos endpoints al backend (después de los endpoints existentes)

# Endpoint para obtener usuario por ID (necesario para edición)
@app.get("/api/users/{user_id}", response_model=UserOut)
def get_user_by_id(user_id: int, db: Session = Depends(get_db)):
    """Obtener usuario por ID"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return user

# Corregir el endpoint de actualización de usuarios existente
@app.put("/api/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, user_update: UserUpdate, db: Session = Depends(get_db)):
    """Actualizar un usuario existente"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    # Solo actualizar campos no nulos
    for field, value in user_update.dict(exclude_unset=True).items():
        if value is not None:  # Verificar que el valor no sea None
            setattr(user, field, value)
    
    db.commit()
    db.refresh(user)
    return user

# Nuevo endpoint para manejar edición de preguntas (corrige duplicación)
@app.put("/api/questions/{question_id}")
def update_question_fixed(question_id: int, question_update: QuestionUpdate, db: Session = Depends(get_db)):
    """Actualizar una pregunta existente sin duplicación"""
    question = db.query(Question).filter(Question.id == question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Pregunta no encontrada")
    
    try:
        # Iniciar transacción
        db.begin()
        
        # Actualizar campos básicos de la pregunta
        if question_update.question_text is not None:
            question.question_text = question_update.question_text
        if question_update.question_order is not None:
            question.question_order = question_update.question_order
        if question_update.time_limit is not None:
            question.question_limit = question_update.time_limit
        
        # Si se proporcionan nuevas respuestas, reemplazar completamente
        if question_update.answers is not None:
            # Primero eliminar todas las respuestas existentes
            db.query(Answer).filter(Answer.question_id == question_id).delete(synchronize_session=False)
            db.flush()  # Forzar eliminación antes de crear nuevas
            
            # Crear nuevas respuestas
            for answer_data in question_update.answers:
                new_answer = Answer(
                    question_id=question_id,
                    answer_text=answer_data.answer_text,
                    is_correct=answer_data.is_correct,
                    answer_order=answer_data.answer_order
                )
                db.add(new_answer)
        
        # Confirmar todos los cambios
        db.commit()
        return {"message": "Pregunta actualizada exitosamente", "question_id": question_id}
        
    except Exception as e:
        # En caso de error, revertir cambios
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al actualizar pregunta: {str(e)}")

# Endpoint mejorado para obtener un usuario por UNI (evita "undefined")
@app.get("/api/users/by-uni/{uni}", response_model=UserOut)
def get_user_by_uni_safe(uni: str, db: Session = Depends(get_db)):
    """Obtener usuario por UNI con manejo de errores mejorado"""
    if not uni or uni.strip() == "":
        raise HTTPException(status_code=400, detail="UNI no puede estar vacío")
    
    user = db.query(User).filter(User.uni == uni.strip()).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"Usuario con UNI '{uni}' no encontrado")
    return user

# Endpoint para crear/actualizar usuarios de forma segura
@app.post("/api/users/", response_model=UserOut)
def create_or_get_user(user: UserCreate, db: Session = Depends(get_db)):
    """Crear usuario o devolver existente (evita duplicación)"""
    # Validar datos de entrada
    if not user.uni or not user.uni.strip():
        raise HTTPException(status_code=400, detail="UNI es requerido")
    if not user.name or not user.name.strip():
        raise HTTPException(status_code=400, detail="Nombre es requerido")
    
    # Buscar usuario existente
    db_user = db.query(User).filter(User.uni == user.uni.strip()).first()
    
    if db_user:
        # Usuario existe, actualizar nombre si es diferente
        if db_user.name != user.name.strip():
            db_user.name = user.name.strip()
            db.commit()
            db.refresh(db_user)
        return db_user
    
    # Crear nuevo usuario
    try:
        db_user = User(uni=user.uni.strip(), name=user.name.strip())
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al crear usuario: {str(e)}")

# Endpoint mejorado para obtener estadísticas del dashboard
@app.get("/api/statistics/dashboard")
def get_dashboard_statistics_improved(db: Session = Depends(get_db)):
    """Obtener estadísticas mejoradas para el dashboard"""
    try:
        total_quizzes = db.query(Quiz).count()
        active_quizzes = db.query(Quiz).filter(Quiz.is_active == True).count()
        total_users = db.query(User).count()
        total_participations = db.query(Participation).count()
        completed_participations = db.query(Participation).filter(Participation.completed == True).count()
        
        # Calcular tasa de finalización de forma segura
        completion_rate = 0
        if total_participations > 0:
            completion_rate = round((completed_participations / total_participations * 100), 2)
        
        return {
            "total_quizzes": total_quizzes,
            "active_quizzes": active_quizzes,
            "inactive_quizzes": max(0, total_quizzes - active_quizzes),
            "total_users": total_users,
            "total_participations": total_participations,
            "completed_participations": completed_participations,
            "completion_rate": completion_rate
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener estadísticas: {str(e)}")

# Middleware para manejo de errores CORS mejorado
@app.middleware("http")
async def add_cors_headers_improved(request, call_next):
    """Agregar headers CORS mejorados"""
    response = await call_next(request)
    
    # Headers CORS completos
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With"
    response.headers["Access-Control-Max-Age"] = "3600"
    
    return response

# Handler para solicitudes OPTIONS (preflight)
@app.options("/{path:path}")
async def options_handler(path: str):
    """Manejar solicitudes OPTIONS para CORS preflight"""
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With",
            "Access-Control-Max-Age": "3600"
        }
    )

# Search endpoints
@app.get("/api/users/search")
def search_users(q: str, db: Session = Depends(get_db)):
    users = db.query(User).filter(
        (User.name.ilike(f"%{q}%")) | (User.uni.ilike(f"%{q}%"))
    ).all()
    return users

@app.get("/api/quizzes/search")
def search_quizzes(q: str, db: Session = Depends(get_db)):
    quizzes = db.query(Quiz).filter(
        (Quiz.title.ilike(f"%{q}%")) | (Quiz.area.ilike(f"%{q}%"))
    ).all()
    return quizzes

# QR Code generation
@app.get("/api/generate-qr/{quiz_id}")
def generate_qr(quiz_id: int, db: Session = Depends(get_db)):
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz no encontrado")
    
    # Generate QR with quiz URL
    quiz_url = f"https://your-domain.com/quiz/{quiz_id}"
    
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)