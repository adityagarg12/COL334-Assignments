#include <iostream>
#include <sstream>
#include <fstream>
#include <vector>
#include <string>
#include <queue>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <fcntl.h>
#include <cstring>
#include <sys/select.h>

using namespace std;

struct Config {
    string server_ip;
    int server_port;
    string filename;
    int num_clients;
};

struct ClientRequest {
    int clientSocket;
    string request;
};

struct sockaddr_in srv;
fd_set fr, fw, fe; // file descriptor sets for select() -> read, write, exception
int sockfd;
int* nArrClient; // Dynamic array for client sockets
int maxClients; // Maximum number of clients from config
vector<string> words; // Store all words from file
queue<ClientRequest> requestQueue; // Queue for processing requests FIFO

// Simple JSON parser for server config
Config LoadConfig(const string& configFile) {
    Config config;
    config.num_clients = 5; // Default value
    
    ifstream file(configFile);
    
    if (!file.is_open()) {
        cerr << "Failed to open config file: " << configFile << endl;
        exit(1);
    }
    
    string line;
    while (getline(file, line)) {
        // Remove spaces and special characters
        size_t start = line.find_first_not_of(" \t");
        if (start == string::npos) continue;
        line = line.substr(start);
        
        if (line.find("\"server_ip\"") != string::npos) {
            size_t colonPos = line.find(":");
            size_t quoteStart = line.find("\"", colonPos);
            size_t quoteEnd = line.find("\"", quoteStart + 1);
            config.server_ip = line.substr(quoteStart + 1, quoteEnd - quoteStart - 1);
        }
        else if (line.find("\"server_port\"") != string::npos) {
            size_t colonPos = line.find(":");
            string numStr = line.substr(colonPos + 1);
            string cleanNum = "";
            for (char c : numStr) {
                if (isdigit(c)) cleanNum += c;
            }
            config.server_port = stoi(cleanNum);
        }
        else if (line.find("\"filename\"") != string::npos) {
            size_t colonPos = line.find(":");
            size_t quoteStart = line.find("\"", colonPos);
            size_t quoteEnd = line.find("\"", quoteStart + 1);
            config.filename = line.substr(quoteStart + 1, quoteEnd - quoteStart - 1);
        }
        else if (line.find("\"num_clients\"") != string::npos) {
            size_t colonPos = line.find(":");
            string numStr = line.substr(colonPos + 1);
            string cleanNum = "";
            for (char c : numStr) {
                if (isdigit(c)) cleanNum += c;
            }
            config.num_clients = stoi(cleanNum);
        }
    }
    
    file.close();
    return config;
}

void LoadWordsFromFile(const string& filename) {
    ifstream file(filename);
    string content;
    if (file.is_open()) {
        getline(file, content); // Read entire line
        file.close();
        
        // Split by comma
        stringstream ss(content);
        string word;
        while (getline(ss, word, ',')) {
            words.push_back(word);
        }
        cout << "Loaded " << words.size() << " words from " << filename << endl;
    } else {
        cerr << "Failed to open file: " << filename << endl;
    }
}

string ProcessRequest(const string& request, int clientSocket) {
    cout << "Processing request from client socket " << clientSocket << ": " << request << endl;
    
    // Parse request in format "p,k\n"
    size_t commaPos = request.find(',');
    
    if (commaPos == string::npos) {
        return "Invalid request format\n";
    }
    
    try {
        int p = stoi(request.substr(0, commaPos)); // offset
        string secondPart = request.substr(commaPos + 1);
        
        // Remove newline character if present
        if (secondPart.back() == '\n') {
            secondPart.pop_back();
        }
        
        int k = stoi(secondPart); // number of words
        
        cout << "Request: offset=" << p << ", count=" << k << endl;
        
        string response;
        
        // Check if offset is beyond file
        if (p >= (int)words.size()) {
            response = "EOF\n";
        } else {
            // Get k words starting from offset p
            int wordsToSend = min(k, (int)words.size() - p);
            bool reachedEOF = (p + k >= (int)words.size());
            
            for (int i = 0; i < wordsToSend; i++) {
                if (i > 0) response += ",";
                response += words[p + i];
            }
            
            if (reachedEOF) {
                response += ",EOF";
            }
            response += "\n";
        }
        
        cout << "Sending response: " << response;
        return response;
        
    } catch (const exception& e) {
        return "Invalid request format\n";
    }
}

void ProcessQueuedRequests() {
    // Process one request from queue (FIFO)
    if (!requestQueue.empty()) {
        ClientRequest req = requestQueue.front();
        requestQueue.pop();
        
        cout << "Processing queued request from client " << req.clientSocket << endl;
        
        string response = ProcessRequest(req.request, req.clientSocket);
        send(req.clientSocket, response.c_str(), response.length(), 0);
        
        cout << "Response sent to client " << req.clientSocket << endl;
        cout << "Requests remaining in queue: " << requestQueue.size() << endl;
        cout << "*****************************************************" << endl;
    }
}

void ProcessNewMessage(int clientSock) {
    cout << "Processing new message from client socket: " << clientSock << endl;
    char buffer[256] = {0};
    int nRet = recv(clientSock, buffer, sizeof(buffer) - 1, 0);
    
    if (nRet <= 0) {
        cout << "Client disconnected or error occurred, closing connection" << endl;
        close(clientSock);
        // Remove from client array
        for (int i = 0; i < maxClients; i++) {
            if (nArrClient[i] == clientSock) {
                nArrClient[i] = 0;
                break;
            }
        }
        return;
    }
    
    buffer[nRet] = '\0'; // Null terminate
    string request(buffer);
    
    // Add request to queue for FIFO processing
    ClientRequest clientReq;
    clientReq.clientSocket = clientSock;
    clientReq.request = request;
    requestQueue.push(clientReq);
    
    cout << "Request queued from client " << clientSock << endl;
    cout << "Queue size: " << requestQueue.size() << endl;
    cout << "*****************************************************" << endl;
}

void ProcessNewRequest() {
    // Check for new connections first
    if (FD_ISSET(sockfd, &fr)) {
        socklen_t nLen = sizeof(struct sockaddr);
        int nClientSocket = accept(sockfd, NULL, &nLen);
        
        if (nClientSocket > 0) {
            // Put it into client fd_set
            int i;
            for (i = 0; i < maxClients; i++) {
                if (nArrClient[i] == 0) {
                    nArrClient[i] = nClientSocket;
                    cout << "New client connected on socket: " << nClientSocket << endl;
                    send(nClientSocket, "Connected to server successfully\n", 33, 0);
                    break;
                }
            }
            
            if (i == maxClients) {
                cout << "Max clients (" << maxClients << ") reached. Rejecting new client." << endl;
                close(nClientSocket);
            }
        }
    }
    
    // Check for messages from existing clients
    for (int i = 0; i < maxClients; i++) {
        if (nArrClient[i] > 0 && FD_ISSET(nArrClient[i], &fr)) {
            // Got new message from client - queue it
            ProcessNewMessage(nArrClient[i]);
        }
    }
}

int main() {
    // Load configuration
    Config config = LoadConfig("config.json");
    maxClients = config.num_clients;
    
    cout << "Multi-Client Server Configuration:" << endl;
    cout << "IP: " << config.server_ip << endl;
    cout << "Port: " << config.server_port << endl;
    cout << "Filename: " << config.filename << endl;
    cout << "Max Clients: " << config.num_clients << endl << endl;
    
    // Allocate dynamic array for client sockets
    nArrClient = new int[maxClients];
    
    // Load words from file
    LoadWordsFromFile(config.filename);
    
    // Initialize client array
    for (int i = 0; i < maxClients; i++) {
        nArrClient[i] = 0;
    }
    
    // Initialize socket
    sockfd = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (sockfd < 0) {
        cerr << "Socket creation failed" << endl;
        delete[] nArrClient;
        return 1;
    }
    cout << "Socket created successfully " << sockfd << endl;
    
    // Initialize server address structure
    srv.sin_family = AF_INET;
    if (config.server_ip == "INADDR_ANY" || config.server_ip.empty()) {
        srv.sin_addr.s_addr = INADDR_ANY;
    } else {
        srv.sin_addr.s_addr = inet_addr(config.server_ip.c_str());
    }
    srv.sin_port = htons(config.server_port);
    memset(&(srv.sin_zero), 0, 8);
    
    // Set socket to non-blocking
    int flags = fcntl(sockfd, F_GETFL, 0);
    if (flags < 0) {
        cerr << "fcntl() failed" << endl;
        close(sockfd);
        delete[] nArrClient;
        return 1;
    }
    
    if (fcntl(sockfd, F_SETFL, flags | O_NONBLOCK) < 0) {
        cerr << "fcntl(F_SETFL) failed (non-blocking)" << endl;
        close(sockfd);
        delete[] nArrClient;
        return 1;
    }
    cout << "Socket set to non-blocking mode" << endl;
    
    // Set SO_REUSEADDR
    int nOptVal = 1; // Enable reuse
    int nOptLen = sizeof(nOptVal);
    int nRet = setsockopt(sockfd, SOL_SOCKET, SO_REUSEADDR, (const char*)&nOptVal, nOptLen);
    if (nRet < 0) {
        cerr << "setsockopt(SO_REUSEADDR) failed" << endl;
        close(sockfd);
        delete[] nArrClient;
        return 1;
    }
    cout << "setsockopt(SO_REUSEADDR) successful" << endl;
    
    // Bind the socket
    nRet = bind(sockfd, (sockaddr*)&srv, sizeof(sockaddr));
    if (nRet < 0) {
        cerr << "Socket bind to local port failed" << endl;
        close(sockfd);
        delete[] nArrClient;
        return 1;
    }
    cout << "Socket bind successful" << endl;
    
    // Listen for connections
    nRet = listen(sockfd, maxClients); // Use configured max clients
    if (nRet < 0) {
        cerr << "Listen failed" << endl;
        close(sockfd);
        delete[] nArrClient;
        return 1;
    }
    cout << "Server listening on " << config.server_ip << ":" << config.server_port << endl;
    cout << "Ready to accept up to " << maxClients << " concurrent client connections..." << endl;
    
    int nMaxFd = sockfd; // Initialize max fd to the socket fd
    struct timeval tv;
    
    while (true) {
        // Initialize fd_sets for each iteration
        FD_ZERO(&fr); // Initialize the read set
        FD_ZERO(&fw); // Initialize the write set
        FD_ZERO(&fe); // Initialize the exception set
        
        FD_SET(sockfd, &fr); // Add socket fd to the read set
        FD_SET(sockfd, &fe); // Add socket fd to the exception set
        
        nMaxFd = sockfd;
        for (int i = 0; i < maxClients; i++) {
            if (nArrClient[i] > 0) {
                FD_SET(nArrClient[i], &fr); // Add active client fds to the read set
                FD_SET(nArrClient[i], &fe); // Add active client fds to the exception set
                if (nArrClient[i] > nMaxFd) {
                    nMaxFd = nArrClient[i]; // Update max fd if needed
                }
            }
        }
        
        tv.tv_sec = 1; // 1 second timeout
        tv.tv_usec = 0; // 0 microseconds
        
        // Wait for activity on any socket
        nRet = select(nMaxFd + 1, &fr, &fw, &fe, &tv);
        
        if (nRet > 0) {
            // Activity detected - process new connections and messages
            cout << "Activity detected on sockets!" << endl;
            ProcessNewRequest();
        } else if (nRet == 0) {
            // Timeout - process queued requests
            cout << "Timeout - processing queued requests..." << endl;
        } else {
            // Error occurred
            cerr << "select() error" << endl;
        }
        
        // Process one request from queue (FIFO) - this ensures first-come-first-serve
        ProcessQueuedRequests();
        
        // Small delay to prevent busy waiting
        usleep(100000); // 0.1 seconds
    }
    
    // Cleanup
    close(sockfd);
    delete[] nArrClient;
    return 0;
}