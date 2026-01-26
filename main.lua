#version 2

local VERSION = 1
local cache = {}

function updateInt(key, val, force)
    if force or cache[key] ~= val then
        SetInt("savegame.mod." .. key, val)
        cache[key] = val
    end
end

function server.init()
    math.randomseed(os.time())
    shared.user_map = {}
    shared.ShowPlayerMap = 0
    shared.session_id = math.random(1000, 9999)
end

function server.update(dt)
    if not shared.session_id then
        shared.session_id = math.random(1000, 9999)
    end

    local clients = Network.GetClients()
    local map = shared.user_map
    local changed = false

    local activeKeys = {}

    for i, c in ipairs(clients) do
        local uniqueKey = c.name .. "_" .. tostring(c.player)
        activeKeys[uniqueKey] = true

        if not map[uniqueKey] then
            local rndId
            local collision
            
            repeat
                rndId = math.random(100000, 9999999)
                collision = false
                for _, id in pairs(map) do
                    if id == rndId then 
                        collision = true 
                        break 
                    end
                end
            until not collision

            map[uniqueKey] = rndId
            changed = true
        end
    end

    if changed then 
        shared.user_map = map 
    end
end

function client.tick(dt)
    updateInt("version", VERSION)
    if shared.session_id then 
        updateInt("session", shared.session_id) 
    else
        updateInt("session", 0)
    end
    
    local myName = GetUserNickname()
    local myId = 0
    
    if Network and Network.IsConnected() then
        local clients = Network.GetClients()
        for i, c in ipairs(clients) do
            if c.name == myName and c.player == GetPlayer() then
                local uniqueKey = c.name .. "_" .. tostring(c.player)

                if shared.user_map and shared.user_map[uniqueKey] then
                    myId = shared.user_map[uniqueKey]
                end
                break
            end
        end
    else
        if not shared.user_map then shared.user_map = {} end
        if not shared.user_map["local"] then
            shared.user_map["local"] = math.random(100000, 999999)
        end
        myId = shared.user_map["local"]
    end

    updateInt("userid", myId)

    local pos = GetPlayerPos()
    updateInt("pos_x", math.floor(pos[1] * 100))
    updateInt("pos_y", math.floor(pos[2] * 100))
    updateInt("pos_z", math.floor(pos[3] * 100))

    local is_dead = (GetPlayerHealth() <= 0) and 1 or 0
    updateInt("isdead", is_dead)

    local is_owner = 0
    if Network and Network.IsConnected() then
        if Network.GetClients()[1].name == myName then is_owner = 1 end
    else is_owner = 1 end
    updateInt("isowner", is_owner)

    updateInt("global", 0)
    updateInt("showmap", shared.ShowPlayerMap or 0)
    updateInt("echo", 0)
end
