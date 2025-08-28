#include <iostream>
#include <fstream>
#include <sstream>
#include <string>
#include <map>
#include <vector>
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

// Simple JSON parser for client config
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
        else if (line.find("\"k\"") != string::npos) {
            size_t colonPos = line.find(":");
            string numStr = line.substr(colonPos + 1);
            string cleanNum = "";
            for (char c : numStr) {
                if (isdigit(c)) cleanNum += c;
            }
            config.k = stoi(cleanNum);
        }
        else if (line.find("\"p\"") != string::npos) {
            size_t colonPos = line.find(":");
            string numStr = line.substr(colonPos + 1);
            string cleanNum = "";
            for (char c : numStr) {
                if (isdigit(c)) cleanNum += c;
            }
            config.p = stoi(cleanNum);
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

vector<string> ParseResponse(const string& response) {
    vector<string> words;
    stringstream ss(response);
    string word;
    
    while (getline(ss, word, ',')) {
        if (!word.empty() && word != "EOF") {
            // Remove newline if present
            if (word.back() == '\n') {
                word.pop_back();
            }
            words.push_back(word);
        }
    }
    
    return words;
}

void DisplayWordFrequencies(const map<string, int>& wordFrequency) {
    cout << "\n=== Word Frequencies ===" << endl;
    if (wordFrequency.empty()) {
        cout << "No words received." << endl;
    } else {
        for (const auto& pair : wordFrequency) {
            cout << pair.first << ", " << pair.second << endl;
        }
    }
}

int main() {
    // Load configuration
    Config config = LoadConfig("config.json");
    
    cout << "Client Configuration:" << endl;
    cout << "Server IP: " << config.server_ip << endl;
    cout << "Server Port: " << config.server_port << endl;
    cout << "Request: p=" << config.p << ", k=" << config.k << endl;
    cout << "File: " << config.filename << endl << endl;
    
    // Create socket
    int nClientSocket = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (nClientSocket < 0) {
        cerr << "Socket creation failed" << endl;
        return 1;
    }
    cout << "Socket created successfully" << endl;
    
    struct sockaddr_in srv;
    srv.sin_family = AF_INET;
    srv.sin_addr.s_addr = inet_addr(config.server_ip.c_str());
    srv.sin_port = htons(config.server_port);
    memset(&(srv.sin_zero), 0, 8);
    
    // Connect to server
    int nRet = connect(nClientSocket, (struct sockaddr*)&srv, sizeof(srv));
    if (nRet < 0) {
        cerr << "Connection to server failed" << endl;
        close(nClientSocket);
        return 1;
    }
    
    cout << "Connected to server successfully!" << endl;
    
    // Send request in format "p,k\n"
    string request = to_string(config.p) + "," + to_string(config.k) + "\n";
    cout << "Sending request: " << request;
    
    send(nClientSocket, request.c_str(), request.length(), 0);
    
    // Receive response
    char buffer[1024] = {0};
    int bytesReceived = recv(nClientSocket, buffer, sizeof(buffer) - 1, 0);
    
    if (bytesReceived > 0) {
        buffer[bytesReceived] = '\0';
        string response(buffer);
        cout << "Received response: " << response;
        
        // Parse and count word frequencies
        map<string, int> wordFrequency;
        
        // Check for EOF
        if (response == "EOF\n") {
            cout << "Request offset is beyond file size - no words received." << endl;
        } else if (response.find("EOF") != string::npos) {
            cout << "End of file reached in response." << endl;
            
            // Process words before EOF
            vector<string> words = ParseResponse(response);
            cout << "Received " << words.size() << " words: ";
            for (const string& word : words) {
                cout << word << " ";
                wordFrequency[word]++;
            }
            cout << endl;
        } else {
            // Normal response - parse all words
            vector<string> words = ParseResponse(response);
            cout << "Received " << words.size() << " words: ";
            for (const string& word : words) {
                cout << word << " ";
                wordFrequency[word]++;
            }
            cout << endl;
        }
        
        // Display word frequencies
        DisplayWordFrequencies(wordFrequency);
        
    } else {
        cout << "No data received or error occurred." << endl;
    }
    
    // Close connection
    close(nClientSocket);
    cout << "\nConnection closed." << endl;
    
    return 0;
}