from fastapi import FastAPI, Depends, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from typing import List, Dict
from datetime import datetime, timedelta
import models
import schemas
from database import engine, get_db
import uvicorn
from datetime import timedelta
from app.routers import analytics
import os
from auth import verify_api_key
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="BESCO API",
    description="Coffee Bean Management System",
    version="1.0.0"
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 프로덕션에서는 특정 도메인으로 제한
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 시작 시 테이블 생성
models.Base.metadata.create_all(bind=engine)

# 라우터 등록
app.include_router(analytics.router)

# 인증 라우터 등록
from auth_routes import router as auth_router
app.include_router(auth_router)

@app.get("/")
def read_root():
    return {"message": "BESCO API Server"}

@app.post("/migrate-blend-components/")
def migrate_blend_components(db: Session = Depends(get_db), api_key: str = Depends(verify_api_key)):
    """BlendComponent 테이블 생성 마이그레이션"""
    try:
        # 테이블 존재 여부 확인
        check_sql = """
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'blend_components'
        );
        """
        exists = db.execute(text(check_sql)).scalar()
        
        if exists:
            return {"message": "blend_components 테이블이 이미 존재합니다"}
        
        # BlendComponent 테이블 생성
        create_table_sql = """
        CREATE TABLE blend_components (
            id SERIAL PRIMARY KEY,
            blend_id INTEGER NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
            component_id INTEGER NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
            ratio FLOAT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        
        CREATE INDEX idx_blend_components_blend_id ON blend_components(blend_id);
        CREATE INDEX idx_blend_components_component_id ON blend_components(component_id);
        """
        
        db.execute(text(create_table_sql))
        db.commit()
        
        return {"message": "blend_components 테이블이 성공적으로 생성되었습니다"}
    except Exception as e:
        db.rollback()
        print(f"Error creating blend_components table: {e}")
        raise HTTPException(status_code=500, detail=f"Error creating table: {str(e)}")

        # 가장 중요한 테이블들만 우선 처리
        tables = ['customers', 'orders', 'materials', 'material_purchases', 'inventory']
        reset_count = 0
        
        for table in tables:
            try:
                # 최대 ID 조회
                result = db.execute(text(f"SELECT COALESCE(MAX(id), 0) FROM {table}")).scalar()
                max_id = result if result else 0
                
                # 시퀀스 재설정
                sequence_name = f"{table}_id_seq"
                new_value = max_id + 1
                db.execute(text(f"SELECT setval('{sequence_name}', {new_value}, false)"))
                print(f"Reset {sequence_name} to {new_value}")
                reset_count += 1
                
            except Exception as table_error:
                print(f"Error processing table {table}: {table_error}")
                continue
        
        db.commit()
        return {"message": f"Successfully reset {reset_count} sequences"}
    except Exception as e:
        db.rollback()
        print(f"Error fixing sequences: {e}")
        raise HTTPException(status_code=500, detail=f"Error fixing sequences: {str(e)}")

# Customer endpoints (보안 적용)
@app.get("/customers/", response_model=List[schemas.Customer])
def get_customers(db: Session = Depends(get_db), api_key: str = Depends(verify_api_key)):
    try:
        return db.query(models.Customer).all()
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/customers/", response_model=schemas.Customer)
def create_customer(customer: schemas.CustomerCreate, db: Session = Depends(get_db), api_key: str = Depends(verify_api_key)):
    try:
        print(f"Attempting to create customer: {customer.name}")
        
        # 기존 고객 확인
        db_customer = db.query(models.Customer).filter(models.Customer.name == customer.name).first()
        if db_customer:
            print(f"Customer {customer.name} already exists")
            raise HTTPException(status_code=400, detail="Customer already exists")
        
        # 새 고객 생성
        try:
            from datetime import datetime
            # ID를 명시적으로 설정하지 않고 데이터베이스가 자동 생성하도록 함
            db_customer = models.Customer(
                name=customer.name,
                created_at=datetime.utcnow()
            )
            print(f"Customer model created: {db_customer.name}")
        except Exception as model_error:
            print(f"Error creating customer model: {model_error}")
            raise model_error
        
        try:
            db.add(db_customer)
            db.commit()
            print(f"Customer {customer.name} created successfully")
            return db_customer
        except Exception as db_error:
            print(f"Database error: {db_error}")
            raise db_error
            
    except HTTPException as http_e:
        db.rollback()
        raise http_e
    except Exception as e:
        print(f"Unexpected error creating customer: {type(e).__name__}: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.delete("/customers/{name}")
def delete_customer(name: str, db: Session = Depends(get_db), api_key: str = Depends(verify_api_key)):
    try:
        db_customer = db.query(models.Customer).filter(models.Customer.name == name).first()
        if not db_customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        
        db.delete(db_customer)
        db.commit()
        return {"message": "Customer deleted successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# Order endpoints
@app.get("/orders/", response_model=List[schemas.Order])
def get_orders(
    customer_name: str = None,
    start_date: str = None,
    end_date: str = None,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    try:
        query = db.query(models.Order)
        
        # 거래처 필터링
        if customer_name and customer_name != "전체":
            query = query.filter(models.Order.customer_name == customer_name)
            
        # 기간 필터링
        if start_date:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            query = query.filter(models.Order.order_date >= start)
        if end_date:
            end = datetime.strptime(end_date, "%Y-%m-%d")
            query = query.filter(models.Order.order_date <= end)
            
        # 주문일자 기준 내림차순 정렬
        query = query.order_by(models.Order.order_date.desc())
        
        orders = query.all()
        return orders
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/orders/bulk/")
def get_orders_bulk(
    customer_names: str = None,  # 쉼표로 구분된 고객명 리스트
    start_date: str = None,
    end_date: str = None,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """여러 고객의 주문 데이터를 한 번에 조회 (예측 분석 포함)"""
    try:
        from datetime import timedelta
        
        query = db.query(models.Order)
        
        # 여러 고객 필터링
        if customer_names:
            customer_list = [name.strip() for name in customer_names.split(',')]
            query = query.filter(models.Order.customer_name.in_(customer_list))
            
        # 기간 필터링
        if start_date:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            query = query.filter(models.Order.order_date >= start)
        if end_date:
            end = datetime.strptime(end_date, "%Y-%m-%d")
            query = query.filter(models.Order.order_date <= end)
            
        # 주문일자 기준 내림차순 정렬
        query = query.order_by(models.Order.customer_name, models.Order.order_date.desc())
        
        orders = query.all()
        
        # 고객별로 그룹화 및 예측 분석
        result = {}
        for order in orders:
            customer_name = order.customer_name
            if customer_name not in result:
                result[customer_name] = []
            result[customer_name].append({
                "id": order.id,
                "material_id": order.material_id,
                "material_name": order.material_name,
                "quantity": order.quantity,
                "price_per_kg": order.price_per_kg,
                "total_price": order.total_price,
                "order_date": order.order_date.strftime("%Y-%m-%d") if order.order_date else None,
                "created_at": order.created_at
            })
        
        # 각 고객별 예측 분석 계산 및 추가
        for customer_name in result:
            customer_orders = result[customer_name]
            if not customer_orders:
                continue
                
            # 날짜순 정렬 (오래된 것부터)
            sorted_orders = sorted(customer_orders, key=lambda x: x["order_date"] if x["order_date"] else "1900-01-01")
            
            # 기본 통계 - 같은 날짜 주문을 1건으로 계산
            unique_dates = set(order["order_date"] for order in sorted_orders if order["order_date"])
            total_orders = len(unique_dates)
            total_quantity = sum(order["quantity"] for order in sorted_orders)
            avg_quantity = total_quantity / total_orders if total_orders > 0 else 0
            
            # 마지막 주문일
            last_order_date = sorted_orders[-1]["order_date"] if sorted_orders else None
            
            # 주문 간격 계산 - 고유 날짜만 사용
            unique_dates_list = sorted(list(unique_dates))
            intervals = []
            if len(unique_dates_list) > 1:
                for i in range(1, len(unique_dates_list)):
                    prev_date = datetime.strptime(unique_dates_list[i-1], "%Y-%m-%d")
                    curr_date = datetime.strptime(unique_dates_list[i], "%Y-%m-%d")
                    interval = (curr_date - prev_date).days
                    if interval > 0:  # 같은 날 주문 제외
                        intervals.append(interval)
            
            avg_interval = sum(intervals) / len(intervals) if intervals else 0
            
            # 다음 예상 주문일
            next_expected_date = None
            d_day = None
            if last_order_date and avg_interval > 0:
                last_date = datetime.strptime(last_order_date, "%Y-%m-%d")
                next_expected_date = (last_date + timedelta(days=int(avg_interval))).strftime("%Y-%m-%d")
                
                # D-DAY 계산 (오늘 기준)
                today = datetime.now().date()
                expected_date = datetime.strptime(next_expected_date, "%Y-%m-%d").date()
                d_day = (expected_date - today).days
            
            # 분석 결과를 고객 데이터에 추가
            result[customer_name] = {
                "orders": customer_orders,
                "마지막주문일": last_order_date,
                "다음예상주문일": next_expected_date,
                "평균주문간격": round(avg_interval, 1) if avg_interval > 0 else 0,
                "평균주문수량": round(avg_quantity, 1),
                "D_DAY": d_day,
                "총주문횟수": total_orders
            }
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def calculate_required_materials(material_id: int, quantity: float, db: Session, check_inventory: bool = True) -> List[dict]:
    """자재 타입에 따른 필요 원재료 계산"""
    material = db.query(models.Material).filter(models.Material.id == material_id).first()
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")

    required_materials = []
    
    if material.type == "blend":
        # 블렌딩 원두의 경우 원재료 비율 계산
        blend_ratio = 1.2  # 10kg 생산에 12kg 원재료 필요
        total_required = quantity * blend_ratio
        
        # 원재료 비율 (고정)
        ratios = {
            "브라질": 0.55,    # 55%
            "콜롬비아": 0.20,  # 20%
            "과테말라": 0.15,  # 15%
            "시다모": 0.10,    # 10%
        }
        
        for name, ratio in ratios.items():
            raw_material = db.query(models.Material).filter(
                models.Material.name == name,
                models.Material.type == "single_origin"  
            ).first()
            
            if raw_material:
                required_materials.append({
                    "id": raw_material.id,
                    "quantity": total_required * ratio
                })
            else:
                raise HTTPException(status_code=400, detail=f"원재료 '{name}'을(를) 찾을 수 없습니다")
    
    elif material.type == "single_origin":
        # 싱글 오리진의 경우 1.23배 사용
        required_materials.append({
            "id": material_id,
            "quantity": quantity * 1.23
        })
    
    else:  # regular
        # 일반 상품은 1:1 비율
        required_materials.append({
            "id": material_id,
            "quantity": quantity
        })
    
    # 재고 확인 (주문 생성 시에만)
    if check_inventory:
        for material in required_materials:
            inventory = db.query(models.Inventory).filter(
                models.Inventory.material_id == material["id"]
            ).first()
            
            if not inventory:
                raise HTTPException(status_code=404, detail=f"Material {material['id']}의 재고 정보를 찾을 수 없습니다")
            
            if inventory.quantity < material["quantity"]:
                material_info = db.query(models.Material).get(material["id"])
                material_name = material_info.name if material_info else f"Material {material['id']}"
                raise HTTPException(
                    status_code=400, 
                    detail=f"{material_name}의 재고가 부족합니다 (필요: {material['quantity']:.1f}kg, 현재: {inventory.quantity:.1f}kg)"
                )
    
    return required_materials

def update_inventory_quantities(materials: List[dict], is_increase: bool, db: Session):
    """재고 수량 업데이트"""
    try:
        for material in materials:
            inventory = db.query(models.Inventory).filter(
                models.Inventory.material_id == material["id"]
            ).first()
            
            if not inventory:
                raise HTTPException(status_code=404, detail=f"Inventory not found for material {material['id']}")
            
            # 증가 또는 감소
            multiplier = 1 if is_increase else -1
            new_quantity = inventory.quantity + (material["quantity"] * multiplier)
            
            if new_quantity < 0:
                material_info = db.query(models.Material).get(material["id"])
                material_name = material_info.name if material_info else f"Material {material['id']}"
                raise HTTPException(
                    status_code=400, 
                    detail=f"{material_name}의 재고가 부족합니다 (필요: {material['quantity']:.1f}kg, 현재: {inventory.quantity:.1f}kg)"
                )
            
            inventory.quantity = new_quantity
            inventory.updated_at = func.now()
            
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"재고 업데이트 중 오류 발생: {str(e)}")

@app.post("/orders/", status_code=201, response_model=schemas.Order)
def create_order(order: schemas.OrderCreate, db: Session = Depends(get_db), api_key: str = Depends(verify_api_key)):
    try:
        # 필요 자재 계산 및 재고 확인
        required_materials = calculate_required_materials(order.material_id, order.quantity, db)
        
        # 주문일자가 문자열인 경우 datetime으로 변환
        order_date = order.order_date
        if isinstance(order_date, str):
            order_date = datetime.strptime(order_date, "%Y-%m-%d")
        
        # 자재 정보 조회
        material = db.query(models.Material).filter(models.Material.id == order.material_id).first()
        if not material:
            raise HTTPException(status_code=404, detail="Material not found")
        
        # 주문 생성
        db_order = models.Order(
            customer_name=order.customer_name,
            material_id=order.material_id,
            material_name=material.name,
            quantity=order.quantity,
            price_per_kg=order.price_per_kg,
            total_price=order.quantity * order.price_per_kg,
            order_date=order_date,
            created_at=func.now()
        )
        db.add(db_order)
        
        # 재고 차감
        update_inventory_quantities(required_materials, False, db)
        
        db.commit()
        db.refresh(db_order)
        
        return db_order
    except HTTPException as e:
        db.rollback()
        raise e
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/orders/{order_id}")
def delete_order(order_id: int, db: Session = Depends(get_db), api_key: str = Depends(verify_api_key)):
    try:
        print(f"Attempting to delete order with ID: {order_id}")
        
        # 주문 조회
        order = db.query(models.Order).filter(models.Order.id == order_id).first()
        if not order:
            print(f"Order with ID {order_id} not found")
            raise HTTPException(status_code=404, detail="Order not found")
        
        print(f"Found order: {order.id}, material_id: {order.material_id}, quantity: {order.quantity}")
        
        # 필요 자재 계산 (삭제니까 같은 수량을 다시 더해줌)
        try:
            required_materials = calculate_required_materials(order.material_id, order.quantity, db, check_inventory=False)
            print(f"Required materials calculated: {required_materials}")
        except Exception as calc_error:
            print(f"Error calculating required materials: {calc_error}")
            raise calc_error
        
        # 재고 증가
        try:
            update_inventory_quantities(required_materials, True, db)
            print("Inventory quantities updated successfully")
        except Exception as inventory_error:
            print(f"Error updating inventory: {inventory_error}")
            raise inventory_error
        
        # 주문 삭제
        try:
            db.delete(order)
            db.commit()
            print(f"Order {order_id} deleted successfully")
        except Exception as delete_error:
            print(f"Error deleting order from database: {delete_error}")
            raise delete_error
        
        return {"message": "Order deleted successfully"}
    except HTTPException as http_e:
        db.rollback()
        raise http_e
    except Exception as e:
        print(f"Unexpected error deleting order: {type(e).__name__}: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# Material endpoints
@app.get("/materials/", response_model=List[schemas.Material])
def get_materials(db: Session = Depends(get_db), api_key: str = Depends(verify_api_key)):
    try:
        materials = db.query(models.Material).all()
        result = []
        
        for material in materials:
            material_dict = {
                "id": material.id,
                "name": material.name,
                "unit": material.unit,
                "type": material.type,
                "processing_ratio": material.processing_ratio,
                "created_at": material.created_at,
                "updated_at": material.updated_at
            }
            result.append(material_dict)
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/materials/{material_id}")
def get_material_by_id_endpoint(material_id: int, db: Session = Depends(get_db), api_key: str = Depends(verify_api_key)):
    try:
        material = db.query(models.Material).filter(models.Material.id == material_id).first()
        if not material:
            raise HTTPException(status_code=404, detail="Material not found")
        
        result = {
            "id": material.id,
            "name": material.name,
            "unit": material.unit,
            "type": material.type,
            "processing_ratio": material.processing_ratio,
            "created_at": material.created_at,
            "updated_at": material.updated_at
        }
        
        # 블렌드 컴포넌트가 있는 경우 함께 조회
        if material.type == "blend":
            blend_components = db.query(models.BlendComponent).filter(
                models.BlendComponent.blend_id == material.id
            ).all()
            result["blend_components"] = [
                {
                    "material_id": comp.component_id,
                    "material_name": comp.material_name,
                    "ratio": comp.ratio
                }
                for comp in blend_components
            ] if blend_components else None
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/materials/", response_model=schemas.Material)
def create_material(material: schemas.MaterialCreate, db: Session = Depends(get_db), api_key: str = Depends(verify_api_key)):
    try:
        print(f"Creating material: {material.dict()}")
        
        # 자재 생성
        db_material = models.Material(
            name=material.name,
            type=material.type,
            unit=material.unit,
            processing_ratio=material.processing_ratio,
            created_at=func.now(),
            updated_at=func.now(),
        )
        db.add(db_material)
        db.flush()  # ID 생성을 위해 flush
        print(f"Material created with ID: {db_material.id}")
        
        # 블렌드 타입인 경우 컴포넌트 추가
        if material.type == "blend" and material.components:
            print(f"Adding blend components: {material.components}")
            for component in material.components:
                db_component = models.BlendComponent(
                    blend_id=db_material.id,
                    component_id=component.component_id,
                    ratio=component.ratio
                )
                db.add(db_component)
        
        # 재고 정보 생성
        db_inventory = models.Inventory(
            material_id=db_material.id,
            quantity=0,
            safety_stock=0,
            created_at=func.now(),
            updated_at=func.now()
        )
        db.add(db_inventory)
        print("Inventory created")
        
        db.commit()
        db.refresh(db_material)
        print("Material creation completed successfully")
        return db_material
    except Exception as e:
        print(f"Error creating material: {type(e).__name__}: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error creating material: {str(e)}")

@app.get("/materials/{material_id}/components", response_model=List[schemas.BlendComponent])
def get_blend_components(material_id: int, db: Session = Depends(get_db), api_key: str = Depends(verify_api_key)):
    """블렌드 자재의 컴포넌트 조회"""
    try:
        material = db.query(models.Material).filter(models.Material.id == material_id).first()
        if not material:
            raise HTTPException(status_code=404, detail="Material not found")
        
        if material.type != "blend":
            raise HTTPException(status_code=400, detail="This material is not a blend type")
        
        components = db.query(models.BlendComponent).filter(
            models.BlendComponent.blend_id == material_id
        ).all()
        
        return components
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/materials/{material_id}/components")
def update_blend_components(
    material_id: int, 
    components: List[schemas.BlendComponentCreate], 
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """블렌드 자재의 컴포넌트 업데이트"""
    try:
        material = db.query(models.Material).filter(models.Material.id == material_id).first()
        if not material:
            raise HTTPException(status_code=404, detail="Material not found")
        
        if material.type != "blend":
            raise HTTPException(status_code=400, detail="This material is not a blend type")
        
        # 기존 컴포넌트 삭제
        db.query(models.BlendComponent).filter(
            models.BlendComponent.blend_id == material_id
        ).delete()
        
        # 새 컴포넌트 추가
        for component in components:
            db_component = models.BlendComponent(
                blend_id=material_id,
                component_id=component.component_id,
                ratio=component.ratio
            )
            db.add(db_component)
        
        db.commit()
        return {"message": "Blend components updated successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/materials/{material_id}/", response_model=schemas.Material)
def update_material(material_id: int, body: dict = Body(...), db: Session = Depends(get_db), api_key: str = Depends(verify_api_key)):
    try:
        db_material = db.query(models.Material).filter(models.Material.id == material_id).first()
        if not db_material:
            raise HTTPException(status_code=404, detail="Material not found")

        # 자재 타입 업데이트
        if "material_type" in body:
            material_type = body["material_type"]
            valid_types = ["regular", "blending", "single"]
            if material_type not in valid_types:
                raise HTTPException(
                    status_code=400,
                    detail=f"잘못된 자재 타입입니다. 가능한 타입: {', '.join(valid_types)}"
                )
            db_material.type = material_type

        # 가공 비율 업데이트
        if "processing_ratio" in body:
            db_material.processing_ratio = float(body["processing_ratio"])

        db_material.updated_at = text('NOW()')
        db.commit()
        db.refresh(db_material)
        return db_material
    except ValueError:
        raise HTTPException(status_code=400, detail="잘못된 값이 입력되었습니다")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/materials/{material_id}/ratio/")
def update_material_ratio(material_id: int, processing_ratio: float = Body(..., embed=True), db: Session = Depends(get_db), api_key: str = Depends(verify_api_key)):
    try:
        db_material = db.query(models.Material).filter(models.Material.id == material_id).first()
        if not db_material:
            raise HTTPException(status_code=404, detail="Material not found")

        db_material.processing_ratio = processing_ratio
        db_material.updated_at = text('NOW()')
        db.commit()
        
        return {"message": "Material ratio updated successfully"}
    except Exception as e:
        print(f"Error updating material ratio: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/materials/{material_id}/ratio/")
def update_material_ratio_api(material_id: int, processing_ratio: float = Body(..., embed=True), db: Session = Depends(get_db)):
    try:
        db_material = db.query(models.Material).filter(models.Material.id == material_id).first()
        if not db_material:
            raise HTTPException(status_code=404, detail="Material not found")

        db_material.processing_ratio = processing_ratio
        db_material.updated_at = text('NOW()')
        db.commit()
        
        return {"message": "Material ratio updated successfully"}
    except Exception as e:
        print(f"Error updating material ratio: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# Material Purchase endpoints
@app.get("/material-purchases/", response_model=List[schemas.MaterialPurchase])
def get_material_purchases(db: Session = Depends(get_db), api_key: str = Depends(verify_api_key)):
    try:
        purchases = db.query(models.MaterialPurchase).order_by(models.MaterialPurchase.purchase_date.desc()).all()
        # 디버깅을 위한 로그
        print(f"Found {len(purchases)} purchases")
        if purchases:
            print(f"First purchase: {purchases[0].__dict__}")
        return purchases
    except Exception as e:
        print(f"Error in get_material_purchases: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/material-purchases/", response_model=schemas.MaterialPurchase)
def create_material_purchase(purchase: schemas.MaterialPurchaseCreate, db: Session = Depends(get_db), api_key: str = Depends(verify_api_key)):
    try:
        print(f"Creating material purchase: {purchase.dict()}")
        
        # 자재 확인
        db_material = db.query(models.Material).filter(models.Material.id == purchase.material_id).first()
        if not db_material:
            raise HTTPException(status_code=404, detail="Material not found")
        print(f"Material found: {db_material.name}")
        
        # 날짜 처리
        if isinstance(purchase.purchase_date, str):
            try:
                # ISO 형식으로 파싱 시도
                purchase_date = datetime.fromisoformat(purchase.purchase_date.replace('Z', '+00:00'))
            except ValueError:
                try:
                    # YYYY-MM-DD 형식으로 파싱 시도
                    purchase_date = datetime.strptime(purchase.purchase_date, "%Y-%m-%d")
                except ValueError:
                    raise HTTPException(status_code=400, detail="Invalid date format. Use ISO 8601 or YYYY-MM-DD")
        else:
            purchase_date = purchase.purchase_date
        print(f"Purchase date processed: {purchase_date}")
        
        # 구매 데이터 생성
        purchase_data = purchase.dict()
        purchase_data["material_name"] = db_material.name  # 자재 이름 추가
        purchase_data["purchase_date"] = purchase_date
        purchase_data["created_at"] = func.now()  # created_at 추가
        
        # 총 가격이 없으면 계산
        if not purchase_data.get("total_price"):
            purchase_data["total_price"] = purchase_data["quantity_kg"] * purchase_data["price_per_kg"]
        
        print(f"Purchase data prepared: {purchase_data}")
        db_purchase = models.MaterialPurchase(**purchase_data)
        db.add(db_purchase)
        db.commit()
        db.refresh(db_purchase)
        print("Material purchase created successfully")
        
        # 재고 업데이트 또는 생성
        db_inventory = db.query(models.Inventory).filter(models.Inventory.material_id == purchase.material_id).first()
        if db_inventory:
            print(f"Updating existing inventory: {db_inventory.quantity} + {purchase.quantity_kg}")
            db_inventory.quantity += purchase.quantity_kg
            db_inventory.updated_at = func.now()
        else:
            print("Creating new inventory record")
            db_inventory = models.Inventory(
                material_id=purchase.material_id,
                quantity=purchase.quantity_kg,
                safety_stock=0,
                created_at=func.now(),
                updated_at=func.now()
            )
            db.add(db_inventory)
        
        db.commit()
        print("Material purchase completed successfully")
        return db_purchase
    except Exception as e:
        print(f"Error creating material purchase: {type(e).__name__}: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error creating material purchase: {str(e)}")

@app.delete("/material-purchases/{purchase_id}")
def delete_material_purchase(purchase_id: int, db: Session = Depends(get_db), api_key: str = Depends(verify_api_key)):
    try:
        # 매입 정보 조회
        db_purchase = db.query(models.MaterialPurchase).filter(models.MaterialPurchase.id == purchase_id).first()
        if not db_purchase:
            raise HTTPException(status_code=404, detail="Material purchase not found")
        
        # 재고 업데이트
        db_inventory = db.query(models.Inventory).filter(models.Inventory.material_id == db_purchase.material_id).first()
        if db_inventory:
            if db_inventory.quantity >= db_purchase.quantity_kg:
                db_inventory.quantity -= db_purchase.quantity_kg
            else:
                raise HTTPException(status_code=400, detail="재고 수량이 부족합니다")
        
        # 매입 삭제
        db.delete(db_purchase)
        db.commit()
        return {"message": "Material purchase deleted successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/purchases/{purchase_id}/")
def delete_purchase(purchase_id: int, db: Session = Depends(get_db), api_key: str = Depends(verify_api_key)):
    purchase = db.query(models.MaterialPurchase).filter(models.MaterialPurchase.id == purchase_id).first()
    if not purchase:
        raise HTTPException(status_code=404, detail="매입 내역을 찾을 수 없습니다")
    
    # 재고 차감
    inventory = db.query(models.Inventory).filter(models.Inventory.material_id == purchase.material_id).first()
    if inventory:
        inventory.quantity = max(0, inventory.quantity - purchase.quantity_kg)
        inventory.updated_at = text('NOW()')
        db.add(inventory)
    
    db.delete(purchase)
    db.commit()
    return {"message": "매입이 삭제되었습니다"}

# Inventory endpoints
@app.post("/migrate-inventory/")
def migrate_inventory(db: Session = Depends(get_db), api_key: str = Depends(verify_api_key)):
    """기존 자재의 재고 데이터 생성"""
    try:
        # 모든 자재 조회
        materials = db.query(models.Material).all()
        migrated_count = 0
        
        for material in materials:
            # 이미 재고가 있는지 확인
            existing = db.query(models.Inventory).filter(
                models.Inventory.material_id == material.id
            ).first()
            
            if not existing:
                # 재고 생성
                db_inventory = models.Inventory(
                    material_id=material.id,
                    quantity=0,
                    safety_stock=0
                )
                db.add(db_inventory)
                migrated_count += 1
        
        db.commit()
        return {"message": f"{migrated_count}개의 재고 데이터가 생성되었습니다"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/inventory/", response_model=List[schemas.Inventory])
def get_inventory(db: Session = Depends(get_db), api_key: str = Depends(verify_api_key)):
    try:
        # material 정보와 함께 조회
        inventories = db.query(models.Inventory).all()
        
        return inventories
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/inventories/{inventory_id}/quantity/")
def update_inventory_quantity(inventory_id: int, quantity: float = Body(..., embed=True), db: Session = Depends(get_db), api_key: str = Depends(verify_api_key)):
    try:
        db_inventory = db.query(models.Inventory).filter(models.Inventory.id == inventory_id).first()
        if not db_inventory:
            raise HTTPException(status_code=404, detail="Inventory not found")

        db_inventory.quantity = quantity
        db_inventory.updated_at = func.now()
        db.commit()
        
        return {"message": "Inventory quantity updated successfully"}
    except Exception as e:
        print(f"Error updating inventory quantity: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/bulk-create-orders/")
def bulk_create_orders(db: Session = Depends(get_db), api_key: str = Depends(verify_api_key)):
    orders_data = [
        {"customer_name": "노원베스코", "order_date": "2024-01-03", "quantity": 30, "price_per_kg": 23000},
        {"customer_name": "더블브이", "order_date": "2024-01-09", "quantity": 30, "price_per_kg": 23000},
        {"customer_name": "노원베스코", "order_date": "2024-01-16", "quantity": 30, "price_per_kg": 23000},
        {"customer_name": "더블브이", "order_date": "2024-01-30", "quantity": 30, "price_per_kg": 23000},
        {"customer_name": "노원베스코", "order_date": "2024-02-06", "quantity": 30, "price_per_kg": 23000},
        {"customer_name": "가우디안경", "order_date": "2024-02-13", "quantity": 4, "price_per_kg": 23000},
        {"customer_name": "더블브이", "order_date": "2024-02-19", "quantity": 30, "price_per_kg": 23000},
        {"customer_name": "노원베스코", "order_date": "2024-02-22", "quantity": 30, "price_per_kg": 23000},
        {"customer_name": "더블브이", "order_date": "2024-03-12", "quantity": 30, "price_per_kg": 23000},
        {"customer_name": "노원베스코", "order_date": "2024-03-16", "quantity": 30, "price_per_kg": 23000},
        {"customer_name": "노원베스코", "order_date": "2024-03-19", "quantity": 30, "price_per_kg": 23000},
        {"customer_name": "더블브이", "order_date": "2024-03-26", "quantity": 30, "price_per_kg": 23000},
        {"customer_name": "동부엔텍", "order_date": "2024-03-28", "quantity": 3, "price_per_kg": 23000},
        {"customer_name": "더블브이", "order_date": "2024-04-16", "quantity": 30, "price_per_kg": 23000},
        {"customer_name": "원스토리", "order_date": "2024-04-21", "quantity": 30, "price_per_kg": 18000},
        {"customer_name": "동부엔텍", "order_date": "2024-04-25", "quantity": 3, "price_per_kg": 23000},
        {"customer_name": "더블브이", "order_date": "2024-05-01", "quantity": 30, "price_per_kg": 23000},
        {"customer_name": "노원베스코", "order_date": "2024-05-07", "quantity": 30, "price_per_kg": 23000},
        {"customer_name": "원스토리", "order_date": "2024-05-08", "quantity": 30, "price_per_kg": 18000},
        {"customer_name": "가우디안경", "order_date": "2024-05-16", "quantity": 4, "price_per_kg": 23000},
        {"customer_name": "동부엔텍", "order_date": "2024-05-20", "quantity": 3, "price_per_kg": 23000},
        {"customer_name": "더블브이", "order_date": "2024-05-22", "quantity": 30, "price_per_kg": 23000},
        {"customer_name": "노원베스코", "order_date": "2024-05-27", "quantity": 30, "price_per_kg": 23000},
        {"customer_name": "원스토리", "order_date": "2024-06-04", "quantity": 30, "price_per_kg": 18000},
        {"customer_name": "더블브이", "order_date": "2024-06-13", "quantity": 30, "price_per_kg": 23000},
        {"customer_name": "동부엔텍", "order_date": "2024-06-26", "quantity": 3, "price_per_kg": 23000},
        {"customer_name": "노원베스코", "order_date": "2024-06-27", "quantity": 30, "price_per_kg": 23000},
        {"customer_name": "원스토리", "order_date": "2024-06-28", "quantity": 30, "price_per_kg": 18000},
        {"customer_name": "더블브이", "order_date": "2024-07-03", "quantity": 30, "price_per_kg": 23000},
        {"customer_name": "노원베스코", "order_date": "2024-07-08", "quantity": 30, "price_per_kg": 23000},
        {"customer_name": "가우디안경", "order_date": "2024-07-16", "quantity": 4, "price_per_kg": 23000},
        {"customer_name": "원스토리", "order_date": "2024-07-18", "quantity": 30, "price_per_kg": 18000},
        {"customer_name": "더블브이", "order_date": "2024-07-23", "quantity": 30, "price_per_kg": 23000},
        {"customer_name": "동부엔텍", "order_date": "2024-07-23", "quantity": 3, "price_per_kg": 23000},
        {"customer_name": "노원베스코", "order_date": "2024-07-29", "quantity": 30, "price_per_kg": 23000},
        {"customer_name": "더블브이", "order_date": "2024-08-12", "quantity": 30, "price_per_kg": 23000},
        {"customer_name": "노원베스코", "order_date": "2024-08-12", "quantity": 30, "price_per_kg": 23000},
        {"customer_name": "원스토리", "order_date": "2024-08-12", "quantity": 30, "price_per_kg": 18000},
        {"customer_name": "백제가", "order_date": "2024-08-14", "quantity": 15, "price_per_kg": 23000},
        {"customer_name": "가우디안경", "order_date": "2024-08-21", "quantity": 4, "price_per_kg": 23000},
        {"customer_name": "동부엔텍", "order_date": "2024-08-26", "quantity": 3, "price_per_kg": 23000},
        {"customer_name": "더블브이", "order_date": "2024-08-30", "quantity": 30, "price_per_kg": 23000},
        {"customer_name": "노원베스코", "order_date": "2024-09-09", "quantity": 30, "price_per_kg": 23000},
        {"customer_name": "원스토리", "order_date": "2024-09-12", "quantity": 30, "price_per_kg": 18000},
        {"customer_name": "더블브이", "order_date": "2024-09-24", "quantity": 30, "price_per_kg": 23000},
        {"customer_name": "동부엔텍", "order_date": "2024-09-30", "quantity": 3, "price_per_kg": 23000},
        {"customer_name": "노원베스코", "order_date": "2024-10-02", "quantity": 30, "price_per_kg": 23000},
        {"customer_name": "가우디안경", "order_date": "2024-10-14", "quantity": 4, "price_per_kg": 23000},
        {"customer_name": "더블브이", "order_date": "2024-10-15", "quantity": 30, "price_per_kg": 23000},
        {"customer_name": "원스토리", "order_date": "2024-10-15", "quantity": 30, "price_per_kg": 18000},
        {"customer_name": "노원베스코", "order_date": "2024-10-23", "quantity": 30, "price_per_kg": 23000},
        {"customer_name": "동부엔텍", "order_date": "2024-10-30", "quantity": 3, "price_per_kg": 23000},
        {"customer_name": "더블브이", "order_date": "2024-11-04", "quantity": 30, "price_per_kg": 23000},
        {"customer_name": "노원베스코", "order_date": "2024-11-11", "quantity": 30, "price_per_kg": 23000},
        {"customer_name": "원스토리", "order_date": "2024-11-18", "quantity": 30, "price_per_kg": 18000},
        {"customer_name": "가우디안경", "order_date": "2024-11-21", "quantity": 4, "price_per_kg": 23000},
        {"customer_name": "더블브이", "order_date": "2024-11-25", "quantity": 30, "price_per_kg": 23000},
        {"customer_name": "죽암리", "order_date": "2024-11-25", "quantity": 4, "price_per_kg": 23000},
        {"customer_name": "노원베스코", "order_date": "2024-12-02", "quantity": 30, "price_per_kg": 23000},
        {"customer_name": "죽암리", "order_date": "2024-12-11", "quantity": 4, "price_per_kg": 23000},
        {"customer_name": "동부엔텍", "order_date": "2024-12-12", "quantity": 3, "price_per_kg": 23000},
        {"customer_name": "노원베스코", "order_date": "2024-12-16", "quantity": 30, "price_per_kg": 23000},
        {"customer_name": "더블브이", "order_date": "2024-12-17", "quantity": 30, "price_per_kg": 23000},
        {"customer_name": "백제가", "order_date": "2024-12-23", "quantity": 15, "price_per_kg": 23000},
        {"customer_name": "원스토리", "order_date": "2024-12-26", "quantity": 30, "price_per_kg": 18000},
        {"customer_name": "죽암리", "order_date": "2025-01-02", "quantity": 4, "price_per_kg": 25000},
        {"customer_name": "더블브이", "order_date": "2025-01-04", "quantity": 30, "price_per_kg": 25000},
        {"customer_name": "노원베스코", "order_date": "2025-01-06", "quantity": 30, "price_per_kg": 25000},
        {"customer_name": "가우디안경", "order_date": "2025-01-13", "quantity": 4, "price_per_kg": 25000},
        {"customer_name": "죽암리", "order_date": "2025-01-14", "quantity": 4, "price_per_kg": 25000},
        {"customer_name": "더블브이", "order_date": "2025-01-21", "quantity": 30, "price_per_kg": 25000},
        {"customer_name": "죽암리", "order_date": "2025-01-21", "quantity": 5, "price_per_kg": 25000},
        {"customer_name": "노원베스코", "order_date": "2025-01-23", "quantity": 30, "price_per_kg": 25000},
        {"customer_name": "동부엔텍", "order_date": "2025-02-04", "quantity": 3, "price_per_kg": 25000},
        {"customer_name": "죽암리", "order_date": "2025-02-07", "quantity": 4, "price_per_kg": 25000},
        {"customer_name": "노원베스코", "order_date": "2025-02-10", "quantity": 30, "price_per_kg": 25000},
        {"customer_name": "원스토리", "order_date": "2025-02-12", "quantity": 30, "price_per_kg": 22000},
        {"customer_name": "더블브이", "order_date": "2025-02-13", "quantity": 30, "price_per_kg": 25000},
        {"customer_name": "노원베스코", "order_date": "2025-02-24", "quantity": 30, "price_per_kg": 25000},
        {"customer_name": "동부엔텍", "order_date": "2025-02-25", "quantity": 3, "price_per_kg": 25000},
        {"customer_name": "원스토리", "order_date": "2025-02-28", "quantity": 30, "price_per_kg": 22000},
    ]

    try:
        # 블렌딩원두 material_id 조회
        material = db.query(models.Material).filter(models.Material.name == "블렌딩원두").first()
        if not material:
            raise HTTPException(status_code=404, detail="블렌딩원두 자재를 찾을 수 없습니다")

        # 각 주문 데이터 처리
        for order_data in orders_data:
            # 거래처 조회 또는 생성
            customer = db.query(models.Customer).filter(models.Customer.name == order_data["customer_name"]).first()
            if not customer:
                customer = models.Customer(name=order_data["customer_name"])
                db.add(customer)
                db.flush()  # ID 생성을 위해 flush

            # 주문 생성
            order = models.Order(
                customer_name=order_data["customer_name"],
                material_id=material.id,
                material_name=material.name,
                quantity=order_data["quantity"],
                price_per_kg=order_data["price_per_kg"],
                total_price=order_data["quantity"] * order_data["price_per_kg"],
                order_date=datetime.strptime(order_data["order_date"], "%Y-%m-%d"),
                created_at=datetime.now(),
            )
            db.add(order)

        db.commit()
        return {"message": "주문 데이터가 성공적으로 추가되었습니다"}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8002))
    uvicorn.run(app, host="0.0.0.0", port=port)
