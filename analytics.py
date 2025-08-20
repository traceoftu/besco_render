from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from app.database import get_db
from app.models import Order, MaterialPurchase

router = APIRouter(prefix="/api/analytics")

@router.get("/profit/summary")
async def get_profit_summary(
    start_date: str = Query(..., description="시작 날짜 (YYYY-MM-DD)"),
    end_date: str = Query(..., description="종료 날짜 (YYYY-MM-DD)"),
    db: Session = Depends(get_db)
):
    try:
        # 매출 데이터 계산
        sales_query = db.query(
            func.sum(Order.total_price).label('total_sales'),
            func.sum(Order.quantity).label('total_quantity')
        ).filter(
            Order.order_date.between(start_date, end_date)
        ).first()

        total_sales = float(sales_query.total_sales or 0)
        total_quantity = float(sales_query.total_quantity or 0)

        # FIFO 방식으로 원가 계산
        cost_query = text("""
            WITH RECURSIVE material_costs AS (
                SELECT 
                    o.id as order_id,
                    o.material_id,
                    o.quantity as order_quantity,
                    o.order_date,
                    mp.price_per_kg,
                    mp.purchase_date
                FROM orders o
                LEFT JOIN material_purchases mp ON o.material_id = mp.material_id
                    AND mp.purchase_date <= o.order_date
                WHERE o.order_date BETWEEN :start_date AND :end_date
                ORDER BY o.order_date, mp.purchase_date DESC
            )
            SELECT 
                SUM(order_quantity * COALESCE(price_per_kg, 0)) as total_cost
            FROM material_costs
        """)
        
        result = db.execute(
            cost_query,
            {"start_date": start_date, "end_date": end_date}
        ).first()
        
        total_cost = float(result.total_cost or 0)
        total_profit = total_sales - total_cost
        profit_rate = (total_profit / total_sales * 100) if total_sales > 0 else 0

        return {
            "total_sales": total_sales,
            "total_cost": total_cost,
            "total_profit": total_profit,
            "profit_rate": profit_rate,
            "total_quantity": total_quantity
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/profit/by-product")
async def get_product_profits(
    start_date: str = Query(..., description="시작 날짜 (YYYY-MM-DD)"),
    end_date: str = Query(..., description="종료 날짜 (YYYY-MM-DD)"),
    db: Session = Depends(get_db)
):
    try:
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

        # FIFO 방식으로 제품별 원가 계산
        cost_query = text("""
            WITH RECURSIVE material_costs AS (
                SELECT 
                    o.material_id,
                    o.material_name,
                    o.quantity as order_quantity,
                    mp.price_per_kg,
                    mp.purchase_date
                FROM orders o
                LEFT JOIN material_purchases mp ON o.material_id = mp.material_id
                    AND mp.purchase_date <= o.order_date
                WHERE o.order_date BETWEEN :start_date AND :end_date
                ORDER BY o.order_date, mp.purchase_date DESC
            )
            SELECT 
                material_id,
                material_name,
                SUM(order_quantity * COALESCE(price_per_kg, 0)) as total_cost
            FROM material_costs
            GROUP BY material_id, material_name
        """)
        
        cost_results = db.execute(
            cost_query,
            {"start_date": start_date, "end_date": end_date}
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
    start_date: str = Query(..., description="시작 날짜 (YYYY-MM-DD)"),
    end_date: str = Query(..., description="종료 날짜 (YYYY-MM-DD)"),
    db: Session = Depends(get_db)
):
    try:
        # 거래처별 매출 집계
        sales_query = db.query(
            Order.customer_name,
            func.sum(Order.total_price).label('sales')
        ).filter(
            Order.order_date.between(start_date, end_date)
        ).group_by(
            Order.customer_name
        ).all()

        # FIFO 방식으로 거래처별 원가 계산
        cost_query = text("""
            WITH RECURSIVE customer_costs AS (
                SELECT 
                    o.customer_name,
                    o.quantity as order_quantity,
                    mp.price_per_kg,
                    mp.purchase_date
                FROM orders o
                LEFT JOIN material_purchases mp ON o.material_id = mp.material_id
                    AND mp.purchase_date <= o.order_date
                WHERE o.order_date BETWEEN :start_date AND :end_date
                ORDER BY o.order_date, mp.purchase_date DESC
            )
            SELECT 
                customer_name,
                SUM(order_quantity * COALESCE(price_per_kg, 0)) as total_cost
            FROM customer_costs
            GROUP BY customer_name
        """)
        
        cost_results = db.execute(
            cost_query,
            {"start_date": start_date, "end_date": end_date}
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
    year: int = Query(..., description="조회할 연도"),
    db: Session = Depends(get_db)
):
    try:
        start_date = f"{year}-01-01"
        end_date = f"{year}-12-31"

        # 월별 매출 집계
        sales_query = db.query(
            func.extract('month', Order.order_date).label('month'),
            func.sum(Order.total_price).label('sales')
        ).filter(
            Order.order_date.between(start_date, end_date)
        ).group_by(
            func.extract('month', Order.order_date)
        ).all()

        # FIFO 방식으로 월별 원가 계산
        cost_query = text("""
            WITH RECURSIVE monthly_costs AS (
                SELECT 
                    EXTRACT(MONTH FROM o.order_date) as month,
                    o.quantity as order_quantity,
                    mp.price_per_kg,
                    mp.purchase_date
                FROM orders o
                LEFT JOIN material_purchases mp ON o.material_id = mp.material_id
                    AND mp.purchase_date <= o.order_date
                WHERE o.order_date BETWEEN :start_date AND :end_date
                ORDER BY o.order_date, mp.purchase_date DESC
            )
            SELECT 
                month,
                SUM(order_quantity * COALESCE(price_per_kg, 0)) as total_cost
            FROM monthly_costs
            GROUP BY month
        """)
        
        cost_results = db.execute(
            cost_query,
            {"start_date": start_date, "end_date": end_date}
        ).fetchall()

        # 결과 조합
        monthly_profits = []
        for sale in sales_query:
            month = int(sale.month)
            cost_result = next(
                (cr for cr in cost_results if int(cr.month) == month),
                None
            )
            
            total_cost = float(cost_result.total_cost if cost_result else 0)
            total_sales = float(sale.sales)
            profit = total_sales - total_cost
            
            monthly_profits.append({
                "month": month,
                "sales": total_sales,
                "cost": total_cost,
                "profit": profit,
                "profit_rate": (profit / total_sales * 100) if total_sales > 0 else 0
            })

        return sorted(monthly_profits, key=lambda x: x["month"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
