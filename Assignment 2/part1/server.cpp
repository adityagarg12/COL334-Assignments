#include <iostream>
#include <sstream>
#include <fstream>
#include <vector>
#include <string>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <cstring>

using namespace std;

struct Config {
    string server_ip;
    int server_port;
    int k;
    int p;
    string filename;
};

vector<string> words;  // Store all words from file

// Simple JSON parser for server config
Config LoadConfig(const string& configFile) {
    Config config;
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
    }
    
    file.close();
    return config;
}

void LoadWordsFromFile(const string& filename) {
    ifstream file(filename);
    string content;
    if (file.is_open()) {
        getline(file, content);  // Read entire line
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

string ProcessRequest(const string& request) {
    cout << "Received request: " << request << endl;
    
    // Parse request in format "p,k\n"
    size_t commaPos = request.find(',');
    
    if (commaPos == string::npos) {
        return "Invalid request format\n";
    }
    
    try {
        int p = stoi(request.substr(0, commaPos));  // offset
        string secondPart = request.substr(commaPos + 1);
        
        // Remove newline character if present
        if (secondPart.back() == '\n') {
            secondPart.pop_back();
        }
        
        int k = stoi(secondPart);  // number of words
        
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

int main() {
    // Load configuration
    Config config = LoadConfig("config.json");
    
    cout << "Server Configuration:" << endl;
    cout << "IP: " << config.server_ip << endl;
    cout << "Port: " << config.server_port << endl;
    cout << "Filename: " << config.filename << endl << endl;
    
    // Load words from file
    LoadWordsFromFile(config.filename);
    
    // Create socket
    int sockfd = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (sockfd < 0) {
        cerr << "Socket creation failed" << endl;
        return 1;
    }
    cout << "Socket created successfully " << sockfd << endl;
    
    // Set SO_REUSEADDR
    int nOptVal = 1;
    int nOptLen = sizeof(nOptVal);
    int nRet = setsockopt(sockfd, SOL_SOCKET, SO_REUSEADDR, (const char*)&nOptVal, nOptLen);
    if (nRet < 0) {
        cerr << "setsockopt(SO_REUSEADDR) failed" << endl;
        close(sockfd);
        return 1;
    }
    cout << "setsockopt(SO_REUSEADDR) successful" << endl;
    
    // Setup server address
    struct sockaddr_in srv;
    srv.sin_family = AF_INET;
    
    if (config.server_ip == "INADDR_ANY" || config.server_ip.empty()) {
        srv.sin_addr.s_addr = INADDR_ANY;
    } else {
        srv.sin_addr.s_addr = inet_addr(config.server_ip.c_str());
    }
    
    srv.sin_port = htons(config.server_port);
    memset(&(srv.sin_zero), 0, 8);
    
    // Bind socket
    nRet = bind(sockfd, (sockaddr*)&srv, sizeof(sockaddr));
    if (nRet < 0) {
        cerr << "Socket bind failed" << endl;
        close(sockfd);
        return 1;
    }
    cout << "Socket bind successful" << endl;
    
    // Listen for connections
    nRet = listen(sockfd, 1); // Only 1 client
    if (nRet < 0) {
        cerr << "Listen failed" << endl;
        close(sockfd);
        return 1;
    }
    cout << "Server listening on " << config.server_ip << ":" << config.server_port << endl;
    cout << "Waiting for client connection..." << endl;
    
    // Accept single client connection
    socklen_t nLen = sizeof(struct sockaddr);
    int clientSocket = accept(sockfd, NULL, &nLen);
    if (clientSocket < 0) {
        cerr << "Accept failed" << endl;
        close(sockfd);
        return 1;
    }
    
    cout << "Client connected successfully on socket: " << clientSocket << endl;
    
    // Handle client requests in a loop
    char buffer[256];
    while (true) {
        memset(buffer, 0, sizeof(buffer));
        int bytesReceived = recv(clientSocket, buffer, sizeof(buffer) - 1, 0);
        
        if (bytesReceived <= 0) {
            cout << "Client disconnected or error occurred" << endl;
            break;
        }
        
        buffer[bytesReceived] = '\0';
        string request(buffer);
        
        // Process the request and get response
        string response = ProcessRequest(request);
        
        // Send response back to client
        send(clientSocket, response.c_str(), response.length(), 0);
        
        cout << "*****************************************************" << endl;
    }
    
    // Cleanup
    close(clientSocket);
    close(sockfd);
    cout << "Server shutting down..." << endl;
    
    return 0;
}