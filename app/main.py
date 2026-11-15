# Trip Service: REST API для учёта заявок на служебные командировки
from datetime import date
from enum import Enum
from typing import Dict, List

from fastapi import APIRouter, FastAPI, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

app = FastAPI(
    title='Trip Service API',
    description='Микросервис оформления служебных командировок работников.',
    version='1.0.0',
    docs_url='/docs',
    openapi_url='/openapi.json',
)


# ---------- Модели данных (DTO) ----------
class RequestStatus(str, Enum):
    REGISTERED = 'registered'
    CLARIFICATION = 'clarification'
    APPROVED = 'approved'
    REJECTED = 'rejected'


class TripRequestCreate(BaseModel):
    # Модель для создания заявки (без служебных полей)
    employee_name: str = Field(
        ..., min_length=1, max_length=100,
        description='ФИО работника', examples=['Петров Пётр Петрович'])
    position: str = Field(
        ..., min_length=1, max_length=100,
        description='Должность работника', examples=['Менеджер'])
    department: str = Field(
        ..., min_length=1, max_length=100,
        description='Подразделение', examples=['Отдел продаж'])
    destination: str = Field(
        ..., min_length=1, max_length=100,
        description='Пункт назначения', examples=['Екатеринбург'])
    purpose: str = Field(
        ..., min_length=1, max_length=300,
        description='Цель командировки', examples=['Переговоры с клиентом'])
    start_date: date = Field(
        ..., description='Дата начала командировки', examples=['2026-11-20'])
    end_date: date = Field(
        ..., description='Дата окончания командировки', examples=['2026-11-22'])
    funding_source: str = Field(
        ..., min_length=1, max_length=100,
        description='Источник финансирования', examples=['Бюджет подразделения'])


class TripRequest(TripRequestCreate):
    # Модель заявки, возвращаемая клиенту
    id: int = Field(..., description='Идентификатор заявки')
    registration_number: str = Field(..., description='Регистрационный номер')
    registered_at: date = Field(..., description='Дата поступления заявки')
    status: RequestStatus = Field(..., description='Статус заявки')


class ErrorResponse(BaseModel):
    detail: str


# ---------- Хранилище в памяти ----------
requests_db: Dict[int, TripRequest] = {}
_id_counter = 0


def _next_id() -> int:
    global _id_counter
    _id_counter += 1
    return _id_counter


def _register(data: TripRequestCreate) -> TripRequest:
    new_id = _next_id()
    item = TripRequest(
        id=new_id,
        registration_number=f'ЗК-{new_id:04d}',
        registered_at=date.today(),
        status=RequestStatus.REGISTERED,
        **data.model_dump(),
    )
    requests_db[item.id] = item
    return item


def _overlaps(new: TripRequestCreate, old: TripRequest) -> bool:
    return (
        old.employee_name == new.employee_name
        and old.status != RequestStatus.REJECTED
        and new.start_date <= old.end_date
        and old.start_date <= new.end_date
    )


def _seed() -> None:
    _register(TripRequestCreate(
        employee_name='Иванов Иван Иванович',
        position='Инженер',
        department='Отдел разработки',
        destination='Казань',
        purpose='Участие в отраслевой конференции',
        start_date=date(2026, 11, 10),
        end_date=date(2026, 11, 14),
        funding_source='Бюджет подразделения',
    ))


_seed()


# ---------- Обработка ошибок валидации ----------
@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            'detail': 'Ошибка валидации входных данных',
            'errors': jsonable_encoder(exc.errors()),
        },
    )


# ---------- Маршрутизация ----------
router = APIRouter(prefix='/api/v1/trip-requests', tags=['Trip requests'])


@router.get(
    '/',
    response_model=List[TripRequest],
    status_code=status.HTTP_200_OK,
    summary='Получить список заявок на командировку',
)
def list_requests() -> List[TripRequest]:
    return list(requests_db.values())


@router.get(
    '/{request_id}',
    response_model=TripRequest,
    status_code=status.HTTP_200_OK,
    summary='Получить заявку по идентификатору',
    responses={
        400: {'model': ErrorResponse, 'description': 'Некорректный id'},
        404: {'model': ErrorResponse, 'description': 'Заявка не найдена'},
    },
)
def get_request(request_id: int) -> TripRequest:
    item = requests_db.get(request_id)
    if item is None:
        raise HTTPException(
            status_code=404, detail=f'Заявка с id={request_id} не найдена')
    return item


@router.post(
    '/',
    response_model=TripRequest,
    status_code=status.HTTP_201_CREATED,
    summary='Зарегистрировать новую заявку на командировку',
    responses={
        400: {'model': ErrorResponse,
              'description': 'Некорректные данные или пересечение сроков'},
    },
)
def create_request(payload: TripRequestCreate) -> TripRequest:
    if payload.end_date < payload.start_date:
        raise HTTPException(
            status_code=400,
            detail='Дата окончания не может быть раньше даты начала')
    if any(_overlaps(payload, old) for old in requests_db.values()):
        raise HTTPException(
            status_code=400,
            detail='Сроки пересекаются с другой командировкой работника')
    return _register(payload)


@router.delete(
    '/{request_id}',
    response_model=TripRequest,
    status_code=status.HTTP_200_OK,
    summary='Удалить заявку на командировку',
    responses={
        400: {'model': ErrorResponse, 'description': 'Некорректный id'},
        404: {'model': ErrorResponse, 'description': 'Заявка не найдена'},
    },
)
def delete_request(request_id: int) -> TripRequest:
    item = requests_db.pop(request_id, None)
    if item is None:
        raise HTTPException(
            status_code=404, detail=f'Заявка с id={request_id} не найдена')
    return item


app.include_router(router)
