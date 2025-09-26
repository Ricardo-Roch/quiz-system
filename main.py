# Version Estable
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from pydantic import BaseModel, Field
from datetime import datetime
import qrcode
import io
import base64
from typing import List, Optional
import os
import logging
from enum import Enum
import shutil
import uuid

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./quiz_app.db")
engine = create_engine(
    DATABASE_URL, 
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    pool_pre_ping=True,
    pool_recycle=300
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Database Models
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    uni = Column(String(50), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    participations = relationship("Participation", back_populates="user", cascade="all, delete-orphan")

class Quiz(Base):
    __tablename__ = "quizzes"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    area = Column(String(100), nullable=False)
    description = Column(Text)
    is_active = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    questions = relationship("Question", back_populates="quiz", cascade="all, delete-orphan")
    participations = relationship("Participation", back_populates="quiz", cascade="all, delete-orphan")

# Agregar nueva columna para tipo de pregunta
class Question(Base):
    __tablename__ = "questions"
    
    id = Column(Integer, primary_key=True, index=True)
    quiz_id = Column(Integer, ForeignKey("quizzes.id", ondelete="CASCADE"))
    question_text = Column(Text, nullable=False)
    question_type = Column(String(20), default="multiple_choice")  # NUEVO: 'multiple_choice', 'open_ended', 'image_choice'
    image_url = Column(String(500), nullable=True)  # NUEVO: Para preguntas con imagen
    question_order = Column(Integer, nullable=False)
    time_limit = Column(Integer, default=30)
    
    quiz = relationship("Quiz", back_populates="questions")
    answers = relationship("Answer", back_populates="question", cascade="all, delete-orphan")

# Agregar columnas para imágenes y respuestas abiertas
class Answer(Base):
    __tablename__ = "answers"
    
    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("questions.id", ondelete="CASCADE"))
    answer_text = Column(String(500), nullable=True)  # MODIFICADO: Ahora nullable
    image_url = Column(String(500), nullable=True)  # NUEVO: Para respuestas con imagen
    is_correct = Column(Boolean, default=False)
    answer_order = Column(Integer, nullable=False)
    
    question = relationship("Question", back_populates="answers")

class Participation(Base):
    __tablename__ = "participations"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    quiz_id = Column(Integer, ForeignKey("quizzes.id", ondelete="CASCADE"))
    score = Column(Integer, default=0)
    total_questions = Column(Integer, default=0)
    completed = Column(Boolean, default=False)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    user = relationship("User", back_populates="participations")
    quiz = relationship("Quiz", back_populates="participations")
    responses = relationship("UserResponse", back_populates="participation", cascade="all, delete-orphan")

# Agregar columna para respuestas abiertas
class UserResponse(Base):
    __tablename__ = "user_responses"
    
    id = Column(Integer, primary_key=True, index=True)
    participation_id = Column(Integer, ForeignKey("participations.id", ondelete="CASCADE"))
    question_id = Column(Integer, ForeignKey("questions.id", ondelete="CASCADE"))
    answer_id = Column(Integer, ForeignKey("answers.id", ondelete="CASCADE"), nullable=True)  # MODIFICADO: Ahora nullable
    open_answer_text = Column(Text, nullable=True)  # NUEVO: Para respuestas abiertas
    response_time = Column(Integer)
    is_correct = Column(Boolean, default=False)
    answered_at = Column(DateTime, default=datetime.utcnow)
    
    participation = relationship("Participation", back_populates="responses")

# Pydantic Models
class UserCreate(BaseModel):
    uni: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)

class UserUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)

class UserOut(BaseModel):
    id: int
    uni: str
    name: str
    created_at: datetime
    
    class Config:
        from_attributes = True

class QuizCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    area: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None

class QuizUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    area: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    is_active: Optional[bool] = None

class QuestionType(str, Enum):
    MULTIPLE_CHOICE = "multiple_choice"
    OPEN_ENDED = "open_ended"
    IMAGE_CHOICE = "image_choice"

class AnswerCreate(BaseModel):
    answer_text: Optional[str] = None
    image_url: Optional[str] = None
    is_correct: bool = False
    answer_order: int = Field(..., ge=1)

class QuestionCreate(BaseModel):
    question_text: str = Field(..., min_length=1)
    question_type: QuestionType = QuestionType.MULTIPLE_CHOICE
    image_url: Optional[str] = None
    question_order: int = Field(..., ge=1)
    time_limit: int = Field(30, ge=10, le=300)
    answers: List[AnswerCreate] = Field(..., min_items=1)  # MODIFICADO: min 1 en lugar de 2

class QuestionUpdate(BaseModel):
    question_text: Optional[str] = Field(None, min_length=1)
    question_type: Optional[QuestionType] = None
    image_url: Optional[str] = None
    question_order: Optional[int] = Field(None, ge=1)
    time_limit: Optional[int] = Field(None, ge=10, le=300)
    answers: Optional[List[AnswerCreate]] = Field(None, min_items=1)

class AnswerOut(BaseModel):
    id: int
    answer_text: Optional[str] = None
    image_url: Optional[str] = None
    answer_order: int
    is_correct: Optional[bool] = None
    
    class Config:
        from_attributes = True

class QuestionOut(BaseModel):
    id: int
    question_text: str
    question_type: str
    image_url: Optional[str] = None
    question_order: int
    time_limit: int
    answers: List[AnswerOut]
    
    class Config:
        from_attributes = True

class QuizOut(BaseModel):  # ← ESTA ES LA CLASE FALTANTE
    id: int
    title: str
    area: str
    description: Optional[str] = None
    is_active: bool
    created_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class QuizDetailOut(BaseModel):
    id: int
    title: str
    area: str
    description: Optional[str] = None
    is_active: bool
    questions: List[QuestionOut]
    
    class Config:
        from_attributes = True

class SubmitAnswer(BaseModel):
    question_id: int
    answer_id: Optional[int] = None  # MODIFICADO: Ahora opcional
    open_answer_text: Optional[str] = None  # NUEVO: Para respuestas abiertas
    response_time: int = Field(..., ge=0)

class ParticipationOut(BaseModel):
    id: int
    quiz_title: str
    quiz_id: int
    user_name: str
    user_uni: str
    score: int
    total_questions: int
    percentage: float
    completed: bool
    started_at: datetime
    completed_at: Optional[datetime]
    
    class Config:
        from_attributes = True

# Create tables
try:
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created successfully")
except Exception as e:
    logger.error(f"Error creating database tables: {e}")

# FastAPI app
app = FastAPI(
    title="Quiz System API", 
    version="1.0.0",
    description="Sistema de Quiz con administración completa"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
)

# Mount static files
try:
    if os.path.exists("static"):
        app.mount("/static", StaticFiles(directory="static"), name="static")
        logger.info("Static files mounted")
except Exception as e:
    logger.warning(f"Could not mount static files: {e}")

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()



# Health check endpoints
@app.get("/api/health")
def health_check():
    try:
        # Test database connection
        db = SessionLocal()
        db.execute("SELECT 1")
        db.close()
        return {
            "status": "healthy", 
            "message": "API funcionando correctamente",
            "database": "connected",
            "timestamp": datetime.utcnow()
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Servicio no disponible")

@app.get("/favicon.ico")
def get_favicon():
    return Response(status_code=204)

@app.get("/")
def read_root():
    try:
        if os.path.exists("static/index.html"):
            return FileResponse("static/index.html")
        else:
            return {
                "message": "Quiz System API is running",
                "docs": "/docs",
                "health": "/api/health"
            }
    except Exception:
        return {
            "message": "Quiz System API is running",
            "docs": "/docs",
            "health": "/api/health"
        }

# User endpoints
@app.post("/api/users/", response_model=UserOut)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    try:
        # Check if user already exists
        db_user = db.query(User).filter(User.uni == user.uni).first()
        if db_user:
            return db_user
        
        # Create new user
        db_user = User(uni=user.uni, name=user.name)
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        logger.info(f"New user created: {user.uni}")
        return db_user
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating user: {e}")
        raise HTTPException(status_code=500, detail="Error al crear usuario")

@app.get("/api/users/", response_model=List[UserOut])
def get_all_users(db: Session = Depends(get_db)):
    try:
        users = db.query(User).order_by(User.created_at.desc()).all()
        return users
    except Exception as e:
        logger.error(f"Error fetching users: {e}")
        raise HTTPException(status_code=500, detail="Error al obtener usuarios")

@app.get("/api/users/{user_id}", response_model=UserOut)
def get_user_by_id(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return user

@app.get("/api/users/by-uni/{uni}", response_model=UserOut)
def get_user_by_uni(uni: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.uni == uni).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return user

@app.put("/api/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, user_update: UserUpdate, db: Session = Depends(get_db)):
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        
        for field, value in user_update.dict(exclude_unset=True).items():
            if value is not None:
                setattr(user, field, value)
        
        db.commit()
        db.refresh(user)
        return user
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating user: {e}")
        raise HTTPException(status_code=500, detail="Error al actualizar usuario")

@app.delete("/api/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db)):
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        
        db.delete(user)
        db.commit()
        return {"message": "Usuario eliminado exitosamente"}
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting user: {e}")
        raise HTTPException(status_code=500, detail="Error al eliminar usuario")

@app.get("/api/users/{uni}/participations", response_model=List[ParticipationOut])
def get_user_participations(uni: str, db: Session = Depends(get_db)):
    try:
        user = db.query(User).filter(User.uni == uni).first()
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        
        participations = db.query(Participation).join(Quiz).filter(Participation.user_id == user.id).all()
        
        result = []
        for p in participations:
            percentage = (p.score / p.total_questions * 100) if p.total_questions > 0 else 0
            result.append({
                "id": p.id,
                "quiz_title": p.quiz.title,
                "quiz_id": p.quiz_id,
                "user_name": user.name,
                "user_uni": user.uni,
                "score": p.score,
                "total_questions": p.total_questions,
                "percentage": round(percentage, 2),
                "completed": p.completed,
                "started_at": p.started_at,
                "completed_at": p.completed_at
            })
        return result
    except Exception as e:
        logger.error(f"Error fetching user participations: {e}")
        raise HTTPException(status_code=500, detail="Error al obtener participaciones")


# Quiz endpoints
@app.post("/api/quizzes/", response_model=QuizOut)
def create_quiz(quiz: QuizCreate, db: Session = Depends(get_db)):
    try:
        db_quiz = Quiz(title=quiz.title, area=quiz.area, description=quiz.description)
        db.add(db_quiz)
        db.commit()
        db.refresh(db_quiz)
        logger.info(f"New quiz created: {quiz.title}")
        return db_quiz
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating quiz: {e}")
        raise HTTPException(status_code=500, detail="Error al crear quiz")

@app.post("/api/upload-image")
async def upload_image(file: UploadFile = File(...)):
    try:
        # Validar tipo de archivo
        if not file.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="Solo se permiten archivos de imagen")
        
        # Crear directorio si no existe
        upload_dir = "static/images"
        os.makedirs(upload_dir, exist_ok=True)
        
        # Generar nombre único
        file_extension = file.filename.split('.')[-1]
        unique_filename = f"{int(datetime.utcnow().timestamp())}_{uuid.uuid4().hex[:8]}.{file_extension}"
        file_path = os.path.join(upload_dir, unique_filename)
        
        # Guardar archivo
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Retornar URL relativa
        image_url = f"/static/images/{unique_filename}"
        return {"image_url": image_url, "filename": unique_filename}
        
    except Exception as e:
        logger.error(f"Error uploading image: {e}")
        raise HTTPException(status_code=500, detail="Error al subir imagen")
    
@app.get("/api/quizzes/", response_model=List[QuizOut])
def get_quizzes(active_only: bool = False, db: Session = Depends(get_db)):
    try:
        query = db.query(Quiz)
        if active_only:
            query = query.filter(Quiz.is_active == True)
        
        quizzes = query.order_by(Quiz.created_at.desc()).all()
        
        return quizzes   # ← ya coincide con QuizOut
    
    except Exception as e:
        logger.error(f"Error in get_quizzes: {e}")
        return []

@app.get("/api/quizzes/count")
def get_quizzes_count(db: Session = Depends(get_db)):
    try:
        total_count = db.query(Quiz).count()
        active_count = db.query(Quiz).filter(Quiz.is_active == True).count()
        return {
            "total_count": total_count,
            "active_count": active_count,
            "inactive_count": total_count - active_count
        }
    except Exception as e:
        logger.error(f"Database error: {e}")
        return {"total_count": 0, "active_count": 0, "inactive_count": 0, "error": str(e)}

@app.get("/api/quizzes/{quiz_id}", response_model=QuizDetailOut)
def get_quiz(quiz_id: int, db: Session = Depends(get_db)):
    try:
        quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
        if not quiz:
            raise HTTPException(status_code=404, detail="Quiz no encontrado")
        
        # FUNCIÓN HELPER PARA LIMPIAR TEXTO
        def clean_text(text):
            if not text:
                return text
            # Escapar caracteres problemáticos
            return (text
                .replace('\n', '\\n')
                .replace('\r', '\\r')
                .replace('\t', '\\t')
                .replace('"', '\\"')
                .replace('\b', '\\b')
                .replace('\f', '\\f')
                .strip())
        
        # Eager load questions and answers con limpieza de texto
        questions = []
        for q in sorted(quiz.questions, key=lambda x: x.question_order):
            answers = []
            for a in sorted(q.answers, key=lambda x: x.answer_order):
                answers.append({
                    "id": a.id, 
                    "answer_text": clean_text(a.answer_text), 
                    "image_url": a.image_url,
                    "answer_order": a.answer_order,
                    "is_correct": a.is_correct
                })
            questions.append({
                "id": q.id,
                "question_text": clean_text(q.question_text),
                "question_type": q.question_type or "multiple_choice",
                "image_url": q.image_url,
                "question_order": q.question_order,
                "time_limit": q.time_limit,
                "answers": answers
            })
        
        return {
            "id": quiz.id,
            "title": clean_text(quiz.title),
            "area": clean_text(quiz.area),
            "description": clean_text(quiz.description),
            "is_active": quiz.is_active,
            "questions": questions
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching quiz: {e}")
        raise HTTPException(status_code=500, detail="Error al obtener quiz")

@app.put("/api/quizzes/{quiz_id}", response_model=QuizOut)
def update_quiz(quiz_id: int, quiz_update: QuizUpdate, db: Session = Depends(get_db)):
    try:
        quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
        if not quiz:
            raise HTTPException(status_code=404, detail="Quiz no encontrado")
        
        for field, value in quiz_update.dict(exclude_unset=True).items():
            if value is not None:
                setattr(quiz, field, value)
        
        db.commit()
        db.refresh(quiz)
        return quiz
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating quiz: {e}")
        raise HTTPException(status_code=500, detail="Error al actualizar quiz")

@app.delete("/api/quizzes/{quiz_id}")
def delete_quiz(quiz_id: int, db: Session = Depends(get_db)):
    try:
        quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
        if not quiz:
            raise HTTPException(status_code=404, detail="Quiz no encontrado")
        
        db.delete(quiz)
        db.commit()
        return {"message": "Quiz eliminado exitosamente"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting quiz: {e}")
        raise HTTPException(status_code=500, detail="Error al eliminar quiz")

# Question endpoints
@app.post("/api/quizzes/{quiz_id}/questions")
def add_question(quiz_id: int, question: QuestionCreate, db: Session = Depends(get_db)):
    try:
        quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
        if not quiz:
            raise HTTPException(status_code=404, detail="Quiz no encontrado")
        
        # Validaciones específicas por tipo
        if question.question_type == QuestionType.MULTIPLE_CHOICE or question.question_type == QuestionType.IMAGE_CHOICE:
            correct_answers = [a for a in question.answers if a.is_correct]
            if len(correct_answers) < 1:
                raise HTTPException(status_code=400, detail="Debe haber al menos una respuesta correcta")
        elif question.question_type == QuestionType.OPEN_ENDED:
            if len(question.answers) != 1:
                raise HTTPException(status_code=400, detail="Las preguntas abiertas deben tener exactamente una 'respuesta' como referencia")
        
        db_question = Question(
            quiz_id=quiz_id,
            question_text=question.question_text,
            question_type=question.question_type,
            image_url=question.image_url,
            question_order=question.question_order,
            time_limit=question.time_limit
        )
        db.add(db_question)
        db.flush()
        
        # Agregar respuestas
        for answer in question.answers:
            db_answer = Answer(
                question_id=db_question.id,
                answer_text=answer.answer_text,
                image_url=answer.image_url,
                is_correct=answer.is_correct if question.question_type != QuestionType.OPEN_ENDED else False,
                answer_order=answer.answer_order
            )
            db.add(db_answer)
        
        db.commit()
        return {"message": "Pregunta agregada exitosamente", "question_id": db_question.id}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error adding question: {e}")
        raise HTTPException(status_code=500, detail="Error al agregar pregunta")


@app.get("/api/questions/{question_id}")
def get_question(question_id: int, db: Session = Depends(get_db)):
    try:
        question = db.query(Question).filter(Question.id == question_id).first()
        if not question:
            raise HTTPException(status_code=404, detail="Pregunta no encontrada")
        
        answers = []
        for a in sorted(question.answers, key=lambda x: x.answer_order):
            answers.append({
                "id": a.id, 
                "answer_text": a.answer_text, 
                "is_correct": a.is_correct, 
                "answer_order": a.answer_order
            })
        
        return {
            "id": question.id,
            "question_text": question.question_text,
            "question_order": question.question_order,
            "time_limit": question.time_limit,
            "answers": answers
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching question: {e}")
        raise HTTPException(status_code=500, detail="Error al obtener pregunta")

@app.put("/api/questions/{question_id}")
def update_question(question_id: int, question_update: QuestionUpdate, db: Session = Depends(get_db)):
    try:
        question = db.query(Question).filter(Question.id == question_id).first()
        if not question:
            raise HTTPException(status_code=404, detail="Pregunta no encontrada")
        
        # Actualizar campos básicos
        if question_update.question_text is not None:
            question.question_text = question_update.question_text
        if question_update.question_order is not None:
            question.question_order = question_update.question_order
        if question_update.time_limit is not None:
            question.time_limit = question_update.time_limit
        
        # Actualizar respuestas si se envían
        if question_update.answers is not None:
            # Validar al menos una correcta
            correct_answers = [a for a in question_update.answers if a.is_correct]
            if len(correct_answers) < 1:
                raise HTTPException(status_code=400, detail="Debe haber al menos una respuesta correcta")
            
            # Eliminar respuestas viejas
            db.query(Answer).filter(Answer.question_id == question_id).delete(synchronize_session=False)
            db.flush()
            
            # Insertar nuevas
            for answer in question_update.answers:
                db_answer = Answer(
                    question_id=question_id,
                    answer_text=answer.answer_text,
                    is_correct=answer.is_correct,
                    answer_order=answer.answer_order
                )
                db.add(db_answer)
        
        db.commit()
        return {"message": "Pregunta actualizada exitosamente", "question_id": question_id}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating question: {e}")
        raise HTTPException(status_code=500, detail="Error al actualizar pregunta")


@app.delete("/api/questions/{question_id}")
def delete_question(question_id: int, db: Session = Depends(get_db)):
    try:
        question = db.query(Question).filter(Question.id == question_id).first()
        if not question:
            raise HTTPException(status_code=404, detail="Pregunta no encontrada")
        
        db.delete(question)
        db.commit()
        return {"message": "Pregunta eliminada exitosamente"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting question: {e}")
        raise HTTPException(status_code=500, detail="Error al eliminar pregunta")

# Participation endpoints
@app.get("/api/users/{uni}/quiz/{quiz_id}/status")
def get_participation_status(uni: str, quiz_id: int, db: Session = Depends(get_db)):
    try:
        user = db.query(User).filter(User.uni == uni).first()
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        
        quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
        if not quiz:
            raise HTTPException(status_code=404, detail="Quiz no encontrado")
        
        participation = db.query(Participation).filter(
            Participation.user_id == user.id,
            Participation.quiz_id == quiz_id
        ).first()
        
        if not participation:
            return {
                "status": "not_started", 
                "can_participate": quiz.is_active,
                "quiz_active": quiz.is_active
            }
        
        if participation.completed:
            percentage = (participation.score / participation.total_questions * 100) if participation.total_questions > 0 else 0
            return {
                "status": "completed",
                "can_participate": False,
                "score": participation.score,
                "total_questions": participation.total_questions,
                "percentage": round(percentage, 2),
                "completed_at": participation.completed_at
            }
        
        return {
            "status": "in_progress", 
            "can_participate": True,
            "participation_id": participation.id,
            "current_score": participation.score,
            "questions_answered": len(participation.responses)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting participation status: {e}")
        raise HTTPException(status_code=500, detail="Error al obtener estado de participación")

@app.post("/api/participate/{quiz_id}")
def start_participation(quiz_id: int, uni: str, db: Session = Depends(get_db)):
    try:
        # Get user
        user = db.query(User).filter(User.uni == uni).first()
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        
        quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
        if not quiz:
            raise HTTPException(status_code=404, detail="Quiz no encontrado")
        
        if not quiz.is_active:
            raise HTTPException(status_code=400, detail="Quiz no está activo")
        
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
            return {
                "participation_id": existing.id, 
                "message": "Continuando participación existente",
                "total_questions": existing.total_questions
            }
        
        # Create new participation
        total_questions = len(quiz.questions)
        if total_questions == 0:
            raise HTTPException(status_code=400, detail="El quiz no tiene preguntas")
        
        participation = Participation(
            user_id=user.id,
            quiz_id=quiz_id,
            total_questions=total_questions
        )
        db.add(participation)
        db.commit()
        db.refresh(participation)
        
        return {
            "participation_id": participation.id, 
            "total_questions": total_questions,
            "message": "Participación iniciada exitosamente"
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error starting participation: {e}")
        raise HTTPException(status_code=500, detail="Error al iniciar participación")

@app.post("/api/participate/{participation_id}/submit")
def submit_answer(participation_id: int, answer: SubmitAnswer, db: Session = Depends(get_db)):
    try:
        participation = db.query(Participation).filter(Participation.id == participation_id).first()
        if not participation:
            raise HTTPException(status_code=404, detail="Participación no encontrada")
        
        if participation.completed:
            raise HTTPException(status_code=400, detail="Esta participación ya está completada")
        
        # Revisar si ya contestó esa pregunta
        existing_response = db.query(UserResponse).filter(
            UserResponse.participation_id == participation_id,
            UserResponse.question_id == answer.question_id
        ).first()
        
        if existing_response:
            raise HTTPException(status_code=400, detail="Ya respondiste esta pregunta")
        
        # Obtener la pregunta
        question = db.query(Question).filter(Question.id == answer.question_id).first()
        if not question:
            raise HTTPException(status_code=400, detail="Pregunta no válida")
        
        is_correct = False
        
        if question.question_type == QuestionType.OPEN_ENDED:
            # Para preguntas abiertas, no evaluamos corrección
            user_response = UserResponse(
                participation_id=participation_id,
                question_id=answer.question_id,
                answer_id=None,
                open_answer_text=answer.open_answer_text,
                response_time=answer.response_time,
                is_correct=False  # Las preguntas abiertas no se califican automáticamente
            )
        else:
            # Para preguntas de opción múltiple e imágenes
            if not answer.answer_id:
                raise HTTPException(status_code=400, detail="answer_id requerido para este tipo de pregunta")
            
            # Verificar respuesta correcta
            correct_answers = db.query(Answer).filter(
                Answer.question_id == answer.question_id,
                Answer.is_correct == True
            ).all()
            
            correct_answer_ids = {a.id for a in correct_answers}
            is_correct = answer.answer_id in correct_answer_ids
            
            user_response = UserResponse(
                participation_id=participation_id,
                question_id=answer.question_id,
                answer_id=answer.answer_id,
                open_answer_text=None,
                response_time=answer.response_time,
                is_correct=is_correct
            )
        
        db.add(user_response)
        
        # Actualizar score solo para preguntas que se califican automáticamente
        if is_correct:
            participation.score += 1
        
        db.commit()
        
        return {
            "correct": is_correct,
            "current_score": participation.score,
            "question_type": question.question_type
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error submitting answer: {e}")
        raise HTTPException(status_code=500, detail="Error al enviar respuesta")


@app.post("/api/participate/{participation_id}/complete")
def complete_participation(participation_id: int, db: Session = Depends(get_db)):
    try:
        participation = db.query(Participation).filter(Participation.id == participation_id).first()
        if not participation:
            raise HTTPException(status_code=404, detail="Participación no encontrada")
        
        if participation.completed:
            return {
                "message": "Participación ya completada",
                "score": participation.score,
                "total_questions": participation.total_questions,
                "percentage": round((participation.score / participation.total_questions) * 100, 2) if participation.total_questions > 0 else 0
            }
        
        participation.completed = True
        participation.completed_at = datetime.utcnow()
        db.commit()
        
        percentage = (participation.score / participation.total_questions * 100) if participation.total_questions > 0 else 0
        
        return {
            "message": "Participación completada exitosamente",
            "score": participation.score,
            "total_questions": participation.total_questions,
            "percentage": round(percentage, 2)
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error completing participation: {e}")
        raise HTTPException(status_code=500, detail="Error al completar participación")

# Reemplaza la función get_all_participations en tu main.py

@app.get("/api/participations/", response_model=List[ParticipationOut])
def get_all_participations(
    completed_only: bool = False, 
    quiz_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    try:
        # Usar LEFT JOIN para evitar problemas con datos eliminados
        query = (
            db.query(
                Participation.id,
                Participation.quiz_id,
                Participation.user_id,
                Participation.score,
                Participation.total_questions,
                Participation.completed,
                Participation.started_at,
                Participation.completed_at,
                User.name.label('user_name'),
                User.uni.label('user_uni'),
                Quiz.title.label('quiz_title')
            )
            .outerjoin(User, Participation.user_id == User.id)
            .outerjoin(Quiz, Participation.quiz_id == Quiz.id)
        )
        
        if completed_only:
            query = query.filter(Participation.completed == True)
        
        if quiz_id:
            query = query.filter(Participation.quiz_id == quiz_id)
        
        # Agregar order by
        query = query.order_by(Participation.completed_at.desc())
        
        # Ejecutar consulta
        results = query.all()
        
        print(f"DEBUG: Found {len(results)} participations")  # Debug log
        
        if not results:
            print("DEBUG: No participations found")
            return []
        
        # Procesar resultados
        participations_list = []
        for row in results:
            try:
                # Calcular porcentaje
                percentage = 0
                if row.total_questions > 0:
                    percentage = (row.score / row.total_questions) * 100
                
                participation_data = {
                    "id": row.id,
                    "quiz_id": row.quiz_id,
                    "quiz_title": row.quiz_title or "Quiz Eliminado",
                    "user_name": row.user_name or "Usuario Eliminado", 
                    "user_uni": row.user_uni or "N/A",
                    "score": row.score,
                    "total_questions": row.total_questions,
                    "percentage": round(percentage, 2),
                    "completed": row.completed,
                    "started_at": row.started_at,
                    "completed_at": row.completed_at
                }
                
                print(f"DEBUG: Processed participation: {participation_data}")
                participations_list.append(participation_data)
                
            except Exception as e:
                print(f"DEBUG: Error processing row: {e}")
                continue
        
        return participations_list
        
    except Exception as e:
        print(f"DEBUG: Database error in get_all_participations: {e}")
        import traceback
        traceback.print_exc()
        return []

@app.get("/api/participations/{participation_id}/responses")
def get_participation_responses(participation_id: int, db: Session = Depends(get_db)):
    try:
        responses = (
            db.query(UserResponse, Question, Answer, User, Participation)
            .join(Question, UserResponse.question_id == Question.id)
            .join(Answer, UserResponse.answer_id == Answer.id)
            .join(Participation, UserResponse.participation_id == Participation.id)
            .join(User, Participation.user_id == User.id)
            .filter(UserResponse.participation_id == participation_id)
            .all()
        )
        
        result = []
        for ur, q, a, u, p in responses:
            result.append({
                "user_name": u.name,
                "user_uni": u.uni,
                "question_order": q.question_order,
                "question_text": q.question_text,
                "answer_text": a.answer_text,
                "is_correct": ur.is_correct,
                "response_time": ur.response_time,
                "completed_at": p.completed_at
            })
        return result
    except Exception as e:
        logger.error(f"Error fetching responses: {e}")
        raise HTTPException(status_code=500, detail="Error al obtener respuestas")

# También agrega este endpoint de debug para verificar los datos
@app.get("/api/debug/participations")
def debug_participations(db: Session = Depends(get_db)):
    try:
        # Contar registros en cada tabla
        users_count = db.query(User).count()
        quizzes_count = db.query(Quiz).count() 
        participations_count = db.query(Participation).count()
        
        # Obtener algunas participaciones
        sample_participations = db.query(Participation).limit(5).all()
        
        sample_data = []
        for p in sample_participations:
            sample_data.append({
                "id": p.id,
                "user_id": p.user_id,
                "quiz_id": p.quiz_id,
                "score": p.score,
                "completed": p.completed,
                "user_exists": db.query(User).filter(User.id == p.user_id).first() is not None,
                "quiz_exists": db.query(Quiz).filter(Quiz.id == p.quiz_id).first() is not None
            })
        
        return {
            "counts": {
                "users": users_count,
                "quizzes": quizzes_count,
                "participations": participations_count
            },
            "sample_participations": sample_data
        }
        
    except Exception as e:
        return {"error": str(e)}


@app.delete("/api/participations/{participation_id}")
def delete_participation(participation_id: int, db: Session = Depends(get_db)):
    try:
        participation = db.query(Participation).filter(Participation.id == participation_id).first()
        if not participation:
            raise HTTPException(status_code=404, detail="Participación no encontrada")
        
        db.delete(participation)
        db.commit()
        return {"message": "Participación eliminada exitosamente"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting participation: {e}")
        raise HTTPException(status_code=500, detail="Error al eliminar participación")

# Enhanced statistics endpoints
@app.get("/api/statistics/dashboard")
def get_dashboard_statistics(db: Session = Depends(get_db)):
    try:
        # Basic counts
        total_quizzes = db.query(Quiz).count()
        active_quizzes = db.query(Quiz).filter(Quiz.is_active == True).count()
        total_users = db.query(User).count()
        total_participations = db.query(Participation).count()
        completed_participations = db.query(Participation).filter(Participation.completed == True).count()
        
        # Calculate completion rate
        completion_rate = 0
        if total_participations > 0:
            completion_rate = round((completed_participations / total_participations * 100), 2)
        
        # Average score calculation
        avg_score = 0
        if completed_participations > 0:
            completed_parts = db.query(Participation).filter(Participation.completed == True).all()
            total_score = sum((p.score / p.total_questions * 100) for p in completed_parts if p.total_questions > 0)
            avg_score = round(total_score / len(completed_parts), 2) if completed_parts else 0
        
        return {
            "total_quizzes": total_quizzes,
            "active_quizzes": active_quizzes,
            "inactive_quizzes": max(0, total_quizzes - active_quizzes),
            "total_users": total_users,
            "total_participations": total_participations,
            "completed_participations": completed_participations,
            "completion_rate": completion_rate,
            "average_score": avg_score
        }
        
    except Exception as e:
        logger.error(f"Error in get_dashboard_statistics: {e}")
        return {
            "total_quizzes": 0,
            "active_quizzes": 0,
            "inactive_quizzes": 0,
            "total_users": 0,
            "total_participations": 0,
            "completed_participations": 0,
            "completion_rate": 0,
            "average_score": 0,
            "error": "Error al obtener estadísticas"
        }

@app.get("/api/statistics/quiz/{quiz_id}")
def get_quiz_statistics(quiz_id: int, db: Session = Depends(get_db)):
    try:
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
            
            # Calculate difficulty metrics
            question_stats = {}
            for participation in completed_participations:
                for response in participation.responses:
                    q_id = response.question_id
                    if q_id not in question_stats:
                        question_stats[q_id] = {"correct": 0, "total": 0}
                    question_stats[q_id]["total"] += 1
                    if response.is_correct:
                        question_stats[q_id]["correct"] += 1
        else:
            avg_score = 0
            avg_percentage = 0
            question_stats = {}
        
        return {
            "quiz_id": quiz_id,
            "quiz_title": quiz.title,
            "total_participations": total_participations,
            "completed_participations": total_completed,
            "completion_rate": round((total_completed / total_participations * 100), 2) if total_participations > 0 else 0,
            "average_score": round(avg_score, 2),
            "average_percentage": round(avg_percentage, 2),
            "total_questions": len(quiz.questions),
            "question_difficulty": {
                str(q_id): round((stats["correct"] / stats["total"] * 100), 2) 
                for q_id, stats in question_stats.items() if stats["total"] > 0
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting quiz statistics: {e}")
        raise HTTPException(status_code=500, detail="Error al obtener estadísticas del quiz")

# Enhanced responses endpoint
# Obtener todas las respuestas de un quiz (versión correcta)
@app.get("/api/quizzes/{quiz_id}/responses")
def get_quiz_responses(quiz_id: int, db: Session = Depends(get_db)):
    try:
        quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
        if not quiz:
            raise HTTPException(status_code=404, detail="Quiz no encontrado")
        
        # Función para limpiar texto
        def clean_text(text):
            if not text:
                return "N/A"
            return str(text).replace('\n', ' ').replace('\r', ' ').replace('\t', ' ').strip()
        
        # Obtener respuestas con LEFT JOIN para evitar errores
        responses = (
            db.query(
                UserResponse.id,
                UserResponse.is_correct,
                UserResponse.response_time,
                UserResponse.answered_at,
                UserResponse.open_answer_text,
                Question.question_order,
                Question.question_text,
                Question.question_type,
                Answer.answer_text,
                User.name.label("user_name"),
                User.uni.label("user_uni"),
                Participation.completed_at,
                Participation.id.label("participation_id")
            )
            .join(Participation, UserResponse.participation_id == Participation.id)
            .join(User, Participation.user_id == User.id)
            .join(Question, UserResponse.question_id == Question.id)
            .outerjoin(Answer, UserResponse.answer_id == Answer.id)  # LEFT JOIN
            .filter(Participation.quiz_id == quiz_id)
            .all()
        )

        result = []
        for r in responses:
            # Manejar respuestas abiertas y de opción múltiple
            answer_text = "N/A"
            if r.open_answer_text:
                answer_text = clean_text(r.open_answer_text)
            elif r.answer_text:
                answer_text = clean_text(r.answer_text)
            
            result.append({
                "participation_id": r.participation_id,
                "user_name": clean_text(r.user_name) if r.user_name else "Usuario Eliminado",
                "user_uni": clean_text(r.user_uni) if r.user_uni else "N/A",
                "question_order": r.question_order or 0,
                "question_text": clean_text(r.question_text) if r.question_text else "Pregunta eliminada",
                "question_type": r.question_type or "multiple_choice",
                "answer_text": answer_text,
                "is_correct": bool(r.is_correct),
                "response_time": r.response_time or 0,
                "answered_at": r.answered_at,
                "completed_at": r.completed_at,
            })
        
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching quiz responses: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error al obtener respuestas: {str(e)}")
# Bulk operations
@app.post("/api/quizzes/bulk-toggle")
def bulk_toggle_quizzes(quiz_ids: List[int], is_active: bool, db: Session = Depends(get_db)):
    try:
        updated = db.query(Quiz).filter(Quiz.id.in_(quiz_ids)).update(
            {Quiz.is_active: is_active}, synchronize_session=False
        )
        db.commit()
        
        action = "activados" if is_active else "desactivados"
        return {"message": f"{updated} quizzes {action} exitosamente"}
    except Exception as e:
        db.rollback()
        logger.error(f"Error in bulk toggle: {e}")
        raise HTTPException(status_code=500, detail="Error en operación masiva")

@app.delete("/api/quizzes/bulk-delete")
def bulk_delete_quizzes(quiz_ids: List[int], db: Session = Depends(get_db)):
    try:
        deleted = db.query(Quiz).filter(Quiz.id.in_(quiz_ids)).delete(synchronize_session=False)
        db.commit()
        
        return {"message": f"{deleted} quizzes eliminados exitosamente"}
    except Exception as e:
        db.rollback()
        logger.error(f"Error in bulk delete: {e}")
        raise HTTPException(status_code=500, detail="Error en eliminación masiva")

# Search endpoints
@app.get("/api/users/search")
def search_users(q: str, db: Session = Depends(get_db)):
    try:
        if len(q.strip()) < 2:
            return []
        
        users = db.query(User).filter(
            (User.name.ilike(f"%{q}%")) | (User.uni.ilike(f"%{q}%"))
        ).limit(50).all()
        return users
    except Exception as e:
        logger.error(f"Error searching users: {e}")
        return []

@app.get("/api/quizzes/search")
def search_quizzes(q: str, db: Session = Depends(get_db)):
    try:
        if len(q.strip()) < 2:
            return []
        
        quizzes = db.query(Quiz).filter(
            (Quiz.title.ilike(f"%{q}%")) | (Quiz.area.ilike(f"%{q}%"))
        ).limit(50).all()
        return quizzes
    except Exception as e:
        logger.error(f"Error searching quizzes: {e}")
        return []

# QR Code generation
@app.get("/api/generate-qr/{quiz_id}")
def generate_qr(quiz_id: int, db: Session = Depends(get_db)):
    try:
        quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
        if not quiz:
            raise HTTPException(status_code=404, detail="Quiz no encontrado")
        
        # Generate QR with quiz URL - replace with your actual domain
        base_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        quiz_url = f"{base_url}/quiz/{quiz_id}"
        
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
            "url": quiz_url,
            "is_active": quiz.is_active
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating QR: {e}")
        raise HTTPException(status_code=500, detail="Error al generar código QR")

# Enhanced middleware for better error handling and CORS
@app.middleware("http")
async def add_cors_headers_and_error_handling(request, call_next):
    try:
        response = await call_next(request)
        
        # Add CORS headers
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With"
        response.headers["Access-Control-Max-Age"] = "3600"
        
        return response
        
    except Exception as e:
        logger.error(f"Middleware error: {e}")
        return Response(
            content=f'{{"error": "Internal server error", "detail": "{str(e)}"}}',
            status_code=500,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json"
            }
        )

# OPTIONS handler for CORS preflight
@app.options("/{path:path}")
async def options_handler(path: str):
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With",
            "Access-Control-Max-Age": "3600"
        }
    )

if __name__ == "__main__":
    import uvicorn
    
    # Configuration
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    debug = os.getenv("DEBUG", "False").lower() == "true"
    
    logger.info(f"Starting Quiz System API on {host}:{port}")
    uvicorn.run(app, host=host, port=port, reload=debug)