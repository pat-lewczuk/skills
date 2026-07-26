create table customers (id text primary key, email text not null unique);
create table orders (id text primary key, customer_id text references customers (id));
