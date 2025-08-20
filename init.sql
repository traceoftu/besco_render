-- Create database
CREATE DATABASE IF NOT EXISTS besco_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE besco_db;

-- Create customers table
CREATE TABLE IF NOT EXISTS customers (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create product_types table
CREATE TABLE IF NOT EXISTS product_types (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create materials table
CREATE TABLE IF NOT EXISTS materials (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(100) NOT NULL,
    unit VARCHAR(20) DEFAULT 'kg',
    default_ratio DECIMAL(10,2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create product_compositions table
CREATE TABLE IF NOT EXISTS product_compositions (
    product_id INT NOT NULL,
    material_id INT NOT NULL,
    ratio DECIMAL(10,2) NOT NULL,
    is_required BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (product_id, material_id),
    FOREIGN KEY (product_id) REFERENCES product_types(id),
    FOREIGN KEY (material_id) REFERENCES materials(id)
);

-- Create inventory table
CREATE TABLE IF NOT EXISTS inventory (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(100) NOT NULL,
    quantity DECIMAL(10,2) NOT NULL DEFAULT 0,
    safety_stock DECIMAL(10,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Create material_purchases table
CREATE TABLE IF NOT EXISTS material_purchases (
    id INT PRIMARY KEY AUTO_INCREMENT,
    material_id INT NOT NULL,
    material_name VARCHAR(100),
    quantity_kg DECIMAL(10,2) NOT NULL,
    price_per_kg DECIMAL(10,2) NOT NULL,
    total_price DECIMAL(10,2) NOT NULL,
    purchase_date DATE NOT NULL,
    supplier VARCHAR(100),
    note TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (material_id) REFERENCES materials(id)
);

-- Create orders table
CREATE TABLE IF NOT EXISTS orders (
    id INT PRIMARY KEY AUTO_INCREMENT,
    customer_name VARCHAR(100) NOT NULL,
    order_date DATE NOT NULL,
    quantity DECIMAL(10,2) NOT NULL,
    price_per_kg DECIMAL(10,2),
    total_price DECIMAL(10,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes
CREATE INDEX idx_customer_name ON customers(name);
CREATE INDEX idx_material_name ON materials(name);
CREATE INDEX idx_product_type_name ON product_types(name);
CREATE INDEX idx_order_date ON orders(order_date);
CREATE INDEX idx_purchase_date ON material_purchases(purchase_date);
