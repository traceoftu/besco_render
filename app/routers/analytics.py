from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from database import get_db
from models import Order, MaterialPurchase, Material

router = APIRouter(prefix="/api/analytics")

def get_default_date_range():
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    return start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")

@router.get("/profit/summary")
async def get_profit_summary(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    try:
        if not start_date or not end_date:
            start_date, end_date = get_default_date_range()

        # 매출 데이터 계산
        sales_query = db.query(
            func.coalesce(func.sum(Order.total_price), 0.0).label('total_sales'),
            func.coalesce(func.sum(Order.quantity), 0.0).label('total_quantity'),
            func.count(Order.id).label('total_orders')
        ).filter(
            Order.order_date.between(start_date, end_date)
        ).first()

        total_sales = float(sales_query.total_sales)
        total_quantity = float(sales_query.total_quantity)
        total_orders = int(sales_query.total_orders)

        # 블렌딩 원두 주문 수량
        blending_orders = db.query(
            func.coalesce(func.sum(Order.quantity), 0.0).label('quantity')
        ).join(Material, Order.material_id == Material.id).filter(
            Order.order_date.between(start_date, end_date),
            Material.type == 'blend'
        ).first()
        blending_quantity = float(blending_orders.quantity)

        # 블렌딩 원두 원가 계산
        blending_cost_query = text("""
            SELECT COALESCE(calculate_blending_cost(:start_date, :end_date), 0) as blending_cost
        """)
        blending_result = db.execute(
            blending_cost_query,
            {"start_date": start_date, "end_date": end_date}
        ).first()
        blending_cost_per_kg = float(blending_result.blending_cost)

        # 일반 원두 원가 계산 (주문 날짜와 가장 가까운 매입가 기준)
        regular_cost_query = text("""
            WITH latest_purchase AS (
                SELECT 
                    o.id as order_id,
                    o.quantity as order_quantity,
                    COALESCE(
                        (
                            SELECT mp.price_per_kg
                            FROM material_purchases mp
                            WHERE mp.material_id = o.material_id
                            AND mp.purchase_date <= o.order_date
                            ORDER BY mp.purchase_date DESC
                            LIMIT 1
                        ), 0
                    ) as price_per_kg
                FROM orders o
                JOIN materials m ON o.material_id = m.id
                WHERE o.order_date BETWEEN :start_date AND :end_date
                AND m.type != 'blend'
            )
            SELECT COALESCE(SUM(order_quantity * price_per_kg), 0) as total_cost
            FROM latest_purchase
        """)
        
        regular_cost_result = db.execute(
            regular_cost_query,
            {"start_date": start_date, "end_date": end_date}
        ).first()
        regular_cost = float(regular_cost_result.total_cost)

        # 총 원가 계산
        total_cost = (blending_cost_per_kg * blending_quantity) + regular_cost
        
        # 이익 계산
        total_profit = total_sales - total_cost
        profit_rate = (total_profit / total_sales * 100) if total_sales > 0 else 0

        # 부자재 및 임대관리비 계산
        packaging_cost = blending_quantity * 1000  # 봉투비
        shipping_box_cost = (blending_quantity / 15) * 6000  # 택배비+박스비
        order_box_cost = total_orders * 1000  # 주문건당 박스비
        
        # 임대관리비 계산 (월 65만원)
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        months_diff = (end_dt.year - start_dt.year) * 12 + end_dt.month - start_dt.month + 1
        rent_cost = months_diff * 650000

        # 부자재 및 임대관리비 총액
        extra_costs = packaging_cost + shipping_box_cost + order_box_cost + rent_cost
        
        # 순이익 계산 (부자재 및 임대관리비 제외)
        net_profit = total_profit - extra_costs
        net_profit_rate = (net_profit / total_sales * 100) if total_sales > 0 else 0

        return {
            "summary_cards": [
                {"title": "총매출", "value": total_sales, "color": "#4CAF50"},
                {"title": "총매입", "value": total_cost, "color": "#F44336"},
                {"title": "총이익", "value": total_profit, "color": "#2196F3"},
                {"title": "총이익율", "value": profit_rate, "color": "#FFC107", "unit": "%"}
            ],
            "net_profit_cards": [
                {"title": "순이익(비용제외)", "value": net_profit, "color": "#9C27B0"},
                {"title": "순이익율(비용제외)", "value": net_profit_rate, "color": "#FF9800", "unit": "%"}
            ],
            "extra_costs_card": {
                "title": "부자재 및 임대관리비",
                "items": [
                    {"title": "블렌딩원두 봉투비", "description": f"블렌딩원두 {blending_quantity}kg × 1,000원", "value": packaging_cost},
                    {"title": "블렌딩원두 택배/박스비", "description": f"블렌딩원두 {blending_quantity}kg ÷ 15kg × 6,000원", "value": shipping_box_cost},
                    {"title": "주문건 박스비", "description": f"총 주문 {total_orders}건 × 1,000원", "value": order_box_cost},
                    {"title": "임대관리비", "description": f"{months_diff}개월 × 650,000원", "value": rent_cost}
                ],
                "total": extra_costs
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/profit/by-product")
async def get_product_profits(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    try:
        if not start_date or not end_date:
            start_date, end_date = get_default_date_range()

        # 제품별 매출과 수량 집계
        sales_query = db.query(
            Order.material_id,
            Order.material_name,
            func.sum(Order.quantity).label('quantity'),
            func.sum(Order.total_price).label('sales')
        ).filter(
            Order.order_date.between(start_date, end_date)
        ).group_by(
            Order.material_id,
            Order.material_name
        ).all()

        # 블렌딩 원두 원가 계산
        blending_cost_query = text("""
            SELECT COALESCE(calculate_blending_cost(:start_date, :end_date), 0) as blending_cost
        """)
        blending_result = db.execute(
            blending_cost_query,
            {"start_date": start_date, "end_date": end_date}
        ).first()
        blending_cost_per_kg = float(blending_result.blending_cost)

        # 제품별 원가 계산 (주문 날짜와 가장 가까운 매입가 기준)
        cost_query = text("""
            WITH product_costs AS (
                SELECT 
                    o.material_id,
                    o.material_name,
                    o.quantity as order_quantity,
                    m.type as material_type,
                    COALESCE(
                        (
                            SELECT mp.price_per_kg
                            FROM material_purchases mp
                            WHERE mp.material_id = o.material_id
                            AND mp.purchase_date <= o.order_date
                            ORDER BY mp.purchase_date DESC
                            LIMIT 1
                        ), 0
                    ) as price_per_kg
                FROM orders o
                JOIN materials m ON o.material_id = m.id
                WHERE o.order_date BETWEEN :start_date AND :end_date
            )
            SELECT 
                material_id,
                material_name,
                material_type,
                SUM(order_quantity * CASE 
                    WHEN material_type = 'blend' THEN :blending_cost
                    ELSE price_per_kg
                END) as total_cost
            FROM product_costs
            GROUP BY material_id, material_name, material_type
        """)
        
        cost_results = db.execute(
            cost_query,
            {
                "start_date": start_date,
                "end_date": end_date,
                "blending_cost": blending_cost_per_kg
            }
        ).fetchall()

        # 결과 조합
        product_profits = []
        for sale in sales_query:
            cost_result = next(
                (cr for cr in cost_results if cr.material_id == sale.material_id),
                None
            )
            
            total_cost = float(cost_result.total_cost if cost_result else 0)
            total_sales = float(sale.sales)
            profit = total_sales - total_cost
            
            product_profits.append({
                "material_id": sale.material_id,
                "material_name": sale.material_name,
                "quantity": float(sale.quantity),
                "sales": total_sales,
                "cost": total_cost,
                "profit": profit,
                "profit_rate": (profit / total_sales * 100) if total_sales > 0 else 0
            })

        return sorted(product_profits, key=lambda x: x["profit"], reverse=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/profit/by-customer")
async def get_customer_profits(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    try:
        if not start_date or not end_date:
            start_date, end_date = get_default_date_range()

        # 거래처별 매출 집계
        sales_query = db.query(
            Order.customer_name,
            func.sum(Order.total_price).label('sales')
        ).filter(
            Order.order_date.between(start_date, end_date)
        ).group_by(
            Order.customer_name
        ).all()

        # 블렌딩 원두 원가 계산
        blending_cost_query = text("""
            SELECT COALESCE(calculate_blending_cost(:start_date, :end_date), 0) as blending_cost
        """)
        blending_result = db.execute(
            blending_cost_query,
            {"start_date": start_date, "end_date": end_date}
        ).first()
        blending_cost_per_kg = float(blending_result.blending_cost)

        # 거래처별 원가 계산 (주문 날짜와 가장 가까운 매입가 기준)
        cost_query = text("""
            WITH customer_costs AS (
                SELECT 
                    o.customer_name,
                    o.quantity as order_quantity,
                    m.type as material_type,
                    COALESCE(
                        (
                            SELECT mp.price_per_kg
                            FROM material_purchases mp
                            WHERE mp.material_id = o.material_id
                            AND mp.purchase_date <= o.order_date
                            ORDER BY mp.purchase_date DESC
                            LIMIT 1
                        ), 0
                    ) as price_per_kg
                FROM orders o
                JOIN materials m ON o.material_id = m.id
                WHERE o.order_date BETWEEN :start_date AND :end_date
            )
            SELECT 
                customer_name,
                SUM(order_quantity * CASE 
                    WHEN material_type = 'blend' THEN :blending_cost
                    ELSE price_per_kg
                END) as total_cost
            FROM customer_costs
            GROUP BY customer_name
        """)
        
        cost_results = db.execute(
            cost_query,
            {
                "start_date": start_date,
                "end_date": end_date,
                "blending_cost": blending_cost_per_kg
            }
        ).fetchall()

        # 결과 조합
        customer_profits = []
        for sale in sales_query:
            cost_result = next(
                (cr for cr in cost_results if cr.customer_name == sale.customer_name),
                None
            )
            
            total_cost = float(cost_result.total_cost if cost_result else 0)
            total_sales = float(sale.sales)
            profit = total_sales - total_cost
            
            customer_profits.append({
                "customer_name": sale.customer_name,
                "sales": total_sales,
                "cost": total_cost,
                "profit": profit,
                "profit_rate": (profit / total_sales * 100) if total_sales > 0 else 0
            })

        return sorted(customer_profits, key=lambda x: x["profit"], reverse=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/profit/monthly")
async def get_monthly_profits(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    try:
        if not start_date or not end_date:
            start_date, end_date = get_default_date_range()

        # 월별 매출 데이터 계산
        sales_query = db.query(
            func.extract('year', Order.order_date).label('year'),
            func.extract('month', Order.order_date).label('month'),
            func.sum(Order.total_price).label('sales'),
            func.sum(Order.quantity).label('quantity')
        ).filter(
            Order.order_date.between(start_date, end_date)
        ).group_by(
            func.extract('year', Order.order_date),
            func.extract('month', Order.order_date)
        ).all()

        # 블렌딩 원두 원가 계산
        blending_cost_query = text("""
            SELECT COALESCE(calculate_blending_cost(:start_date, :end_date), 0) as blending_cost
        """)
        blending_result = db.execute(
            blending_cost_query,
            {"start_date": start_date, "end_date": end_date}
        ).first()
        blending_cost_per_kg = float(blending_result.blending_cost)

        # 월별 원가 계산 (주문 날짜와 가장 가까운 매입가 기준)
        cost_query = text("""
            WITH monthly_costs AS (
                SELECT 
                    EXTRACT(YEAR FROM o.order_date) as year,
                    EXTRACT(MONTH FROM o.order_date) as month,
                    o.quantity as order_quantity,
                    m.type as material_type,
                    COALESCE(
                        (
                            SELECT mp.price_per_kg
                            FROM material_purchases mp
                            WHERE mp.material_id = o.material_id
                            AND mp.purchase_date <= o.order_date
                            ORDER BY mp.purchase_date DESC
                            LIMIT 1
                        ), 0
                    ) as price_per_kg
                FROM orders o
                JOIN materials m ON o.material_id = m.id
                WHERE o.order_date BETWEEN :start_date AND :end_date
            )
            SELECT 
                year,
                month,
                SUM(order_quantity * CASE 
                    WHEN material_type = 'blend' THEN :blending_cost
                    ELSE price_per_kg
                END) as total_cost
            FROM monthly_costs
            GROUP BY year, month
        """)
        
        cost_results = db.execute(
            cost_query,
            {
                "start_date": start_date,
                "end_date": end_date,
                "blending_cost": blending_cost_per_kg
            }
        ).fetchall()

        # 결과 조합
        monthly_profits = []
        for sale in sales_query:
            year = int(sale.year)
            month = int(sale.month)
            cost_result = next(
                (cr for cr in cost_results if int(cr.year) == year and int(cr.month) == month),
                None
            )
            
            total_cost = float(cost_result.total_cost if cost_result else 0)
            total_sales = float(sale.sales)
            profit = total_sales - total_cost
            
            monthly_profits.append({
                "year": year,
                "month": month,
                "sales": total_sales,
                "cost": total_cost,
                "profit": profit,
                "profit_rate": (profit / total_sales * 100) if total_sales > 0 else 0,
                "quantity": float(sale.quantity)
            })

        return sorted(monthly_profits, key=lambda x: (x["year"], x["month"]))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
