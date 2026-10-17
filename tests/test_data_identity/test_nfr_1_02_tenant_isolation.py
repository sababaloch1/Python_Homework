def test_user_cannot_see_other_org_data(client):
    # 1. Register Org A (User A)
    client.post("/auth/register", json={
        "email": "usera@test.com", "password": "password", "full_name": "User A", "org_name": "Org A"
    })
    
    # 2. Register Org B (User B)
    client.post("/auth/register", json={
        "email": "userb@test.com", "password": "password", "full_name": "User B", "org_name": "Org B"
    })

    # 3. Login as User A and create a facility
    login_a = client.post("/auth/login", data={"username": "usera@test.com", "password": "password"})
    token_a = login_a.json()["access_token"]
    
    client.post("/facilities", headers={"Authorization": f"Bearer {token_a}"}, json={
        "name": "Secret Facility A", "city": "Berlin"
    })

    # 4. Login as User B
    login_b = client.post("/auth/login", data={"username": "userb@test.com", "password": "password"})
    token_b = login_b.json()["access_token"]

    # 5. User B tries to get facilities. They should get an empty list, not User A's facility!
    response = client.get("/facilities", headers={"Authorization": f"Bearer {token_b}"})
    
    assert response.status_code == 200
    assert len(response.json()) == 0  # Tenant isolation works! B sees 0 facilities.